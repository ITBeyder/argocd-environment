import subprocess
import time
import os
import json
import yaml
import socket

from yaml.representer import SafeRepresenter

class LiteralString(str):
    pass

def literal_scalarstring_presenter(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')

yaml.add_representer(LiteralString, literal_scalarstring_presenter)

config_file = "cluster.json"
if os.path.exists(config_file):
    with open(config_file, "r") as f:
        k3s_clusters = json.load(f)
else:
    print(f"❌ Configuration file '{config_file}' not found. Exiting.")
    exit(1)

minikube_cluster_name = "argocd"
yaml_output_file = "./k3s-clusters.yml"

def run_command(command, check=True, capture_output=False, timeout=30):
    try:
        result = subprocess.run(command, shell=True, text=True,
                                capture_output=capture_output, check=check, timeout=timeout)
        return result.stdout.strip() if capture_output else None
    except subprocess.TimeoutExpired:
        print(f"❌ Timeout: Command took too long: {command}")
        return None
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {command}\n{e}")
        return None

def is_minikube_running():
    result = run_command(f"minikube status -p {minikube_cluster_name}", capture_output=True)
    return "Running" in result if result else False

def is_tunnel_running():
    result = run_command("pgrep -f 'minikube.*tunnel'", capture_output=True)
    return bool(result)

def start_minikube():
    if is_minikube_running():
        print("✅ Minikube is already running. Skipping start.")
    else:
        print("🚀 Starting Minikube...")
        run_command(f"minikube start -p {minikube_cluster_name} --memory=4g --cpus=4 --addons ingress")
        print("✅ Minikube started successfully.")

def start_tunnel():
    if is_tunnel_running():
        print("✅ Minikube tunnel is already running. Skipping start.")
    else:
        print("🚀 Opening a new terminal window for Minikube tunnel...")
        subprocess.Popen([
            "osascript", "-e",
            'tell application "Terminal" to do script "sudo minikube -p argocd tunnel; exec $SHELL"'
        ])
        print("⏳ Waiting for Minikube tunnel to start...")
        for _ in range(30): 
            if is_tunnel_running():
                print("✅ Minikube tunnel is now running.")
                break
            time.sleep(1)
        else:
            print("⚠️ Warning: Minikube tunnel did not start within 30 seconds.")

def is_argocd_installed():
    result = run_command("kubectl get deployment -n argocd argocd-server --ignore-not-found",
                         capture_output=True)
    return bool(result.strip())

def is_argocd_server_running():
    result = run_command(
        "kubectl get deployment -n argocd argocd-server -o jsonpath='{.status.readyReplicas}'",
        capture_output=True
    )
    if result and result.isdigit() and int(result) > 0:
        return True
    return False

def install_argocd():
    if is_argocd_installed():
        print("✅ ArgoCD is already installed. Skipping installation.")
    else:
        print("🚀 Creating ArgoCD namespace and installing ArgoCD...")
        run_command("kubectl create ns argocd || true")
        run_command("kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/v2.5.8/manifests/install.yaml")
        print("✅ ArgoCD installed successfully.")
        print("⏳ Waiting for ArgoCD to initialize...")
        
    
        max_retries = 120 
        for i in range(max_retries):
            if is_argocd_server_running():
                print(f"✅ ArgoCD server is running after {i*5} seconds.")
                break
            if i % 12 == 0: 
                print(f"⏳ Still waiting for ArgoCD server to start... ({i*5} seconds passed)")
            time.sleep(5)
        else:
            print("⚠️ Warning: ArgoCD server did not start within the timeout period.")

def get_argocd_admin_password():
    if not is_argocd_server_running():
        print("⚠️ ArgoCD server is not running. Skipping password retrieval.")
        return
        
    print("🔑 Retrieving ArgoCD initial admin password...")
    password = run_command(
        "kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d",
        capture_output=True
    )
    if password:
        with open("argocd_admin_password.txt", "w") as f:
            f.write(password)
        os.environ["argocdsecret"] = password
        print("✅ ArgoCD admin password saved and exported as env variable.")
    else:
        print("❌ Failed to retrieve ArgoCD password.")

def apply_argocd_resources():
    print("🚀 Applying ArgoCD configurations...")
    run_command("kubectl apply -f ./argocd-ingress.yaml")
    run_command("kubectl apply -f ./projects")
    run_command("kubectl apply -f ./repos")
    print("✅ ArgoCD resources applied successfully.")

def is_k3s_running(cluster_name):
    result = run_command(
        f'docker ps --filter "name=k3s-{cluster_name}" --format "{{{{.ID}}}}"',
        capture_output=True
    )
    return bool(result)

def create_k3s_cluster(cluster_name, port):
    if is_k3s_running(cluster_name):
        print(f"✅ K3s cluster {cluster_name} is already running. Skipping creation.")
        return

    print(f"🚀 Creating K3s cluster: {cluster_name} on port {port}")
    volume_name = f"k3s-{cluster_name}-data"
    run_command(f"docker volume create {volume_name}")
    run_command(f'''
        docker run -d --name k3s-{cluster_name} \
          --network {minikube_cluster_name} \
          --privileged \
          -e K3S_KUBECONFIG_OUTPUT=/output/k3s-{cluster_name}.yaml \
          -e K3S_NODE_LABELS="environment={cluster_name}" \
          -p {port}:6443 \
          -v /tmp/k3s-output:/output \
          -v {volume_name}:/var/lib/rancher/k3s \
          rancher/k3s:v1.27.4-k3s1 server
    ''')
    print(f"✅ K3s cluster {cluster_name} created successfully on port {port}.")

def get_k3s_certificates(cluster_name):
    print(f"🔑 Extracting K3s cluster certificates for {cluster_name}...")
    server_ca = run_command(
        f'docker exec k3s-{cluster_name} sh -c "cat /var/lib/rancher/k3s/server/tls/server-ca.crt | base64 -w 0"',
        capture_output=True
    )
    client_admin_crt = run_command(
        f'docker exec k3s-{cluster_name} sh -c "cat /var/lib/rancher/k3s/server/tls/client-admin.crt | base64 -w 0"',
        capture_output=True
    )
    client_admin_key = run_command(
        f'docker exec k3s-{cluster_name} sh -c "cat /var/lib/rancher/k3s/server/tls/client-admin.key | base64 -w 0"',
        capture_output=True
    )

    return {
        "server_ca": server_ca,
        "client_admin_crt": client_admin_crt,
        "client_admin_key": client_admin_key
    }

def get_docker_container_ip(container_name):
    result = run_command(
        f'docker inspect -f "{{{{.NetworkSettings.Networks.{minikube_cluster_name}.IPAddress}}}}" k3s-{container_name}',
        capture_output=True
    )
    if not result:
        result = run_command(
            f'docker inspect -f "{{{{.NetworkSettings.IPAddress}}}}" k3s-{container_name}',
            capture_output=True
        )
    return result

def generate_yaml(clusters_data):
    print(f"📝 Generating YAML file at {yaml_output_file}...")
    
    # Check and create directory only if needed
    output_dir = os.path.dirname(yaml_output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    all_resources = []
    
    for cluster_name, certs in clusters_data.items():
        port = k3s_clusters[cluster_name]
        container_ip = get_docker_container_ip(cluster_name) or "UNKNOWN"
        
        tls_config_json = json.dumps({
            "bearerToken": "",
            "tlsClientConfig": {
                "insecure": False,
                "caData": certs["server_ca"],
                "certData": certs["client_admin_crt"],
                "keyData": certs["client_admin_key"]
            }
        }, indent=2)

        tls_config_literal = LiteralString(tls_config_json)
        
        secret = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": cluster_name,
                "namespace": "argocd",
                "labels": {
                    "argocd.argoproj.io/secret-type": "cluster",
                    "argocd.argoproj.io/auto-label-cluster-info": "true",
                    "environment": cluster_name,
                }
            },
            "type": "Opaque",
            "stringData": {
                "name": cluster_name,
                "server": f"https://{container_ip}:6443",
                "config": tls_config_literal
            }
        }
        
        all_resources.append(secret)

    with open(yaml_output_file, 'w') as f:
        yaml.dump_all(all_resources, f, default_flow_style=False, sort_keys=False)
    
    print(f"✅ YAML file generated successfully at {yaml_output_file}")
    print(f"🔄 Applying generated YAML file to ArgoCD...")
    run_command(f"kubectl apply -f {yaml_output_file}")
    print(f"✅ Cluster configurations applied to ArgoCD successfully.")

    
if __name__ == "__main__":

    start_minikube()
    start_tunnel()
    install_argocd()
    get_argocd_admin_password()
    apply_argocd_resources()

    clusters_data = {}
    for cluster, port in k3s_clusters.items():
        create_k3s_cluster(cluster, port)

    print("⏳ Waiting for K3s clusters to initialize...")
    time.sleep(20)

    for cluster in k3s_clusters.keys():
        certs = get_k3s_certificates(cluster)
        if certs:
            clusters_data[cluster] = {
                "server_ca": certs["server_ca"],
                "client_admin_crt": certs["client_admin_crt"],
                "client_admin_key": certs["client_admin_key"]
            }

    if clusters_data:
        generate_yaml(clusters_data)
    else:
        print("❌ No cluster data collected. Cannot generate YAML file.")