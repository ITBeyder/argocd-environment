
# ArgoCD Environment Setup

This project automates the setup of a local Kubernetes (K3s) environment with Minikube and ArgoCD, allowing easy management of clusters and resources.

## Prerequisites

Before running the script, ensure you have the following installed:

- Docker
- Minikube
- kubectl
- ArgoCD CLI
- Python 3.x with pip

### Install Required Python Packages

```bash
pip install pyyaml
```

## Project Structure

```
argocd-environment/
├── argocd-ingress.yaml
├── projects/             # Project definitions for ArgoCD
├── repos/                # Repository definitions for ArgoCD
├── cluster.json          # JSON file with K3s cluster definitions
├── main.py               # Main script to set up the environment
└── k3s-clusters.yml      # Generated YAML file for K3s clusters
```

### Example cluster.json

```json
{
    "dev": 6444,
    "stage": 6445,
    "prod": 6446
}
```

### Example Project Folder Structure

```
projects/
└── devopsproject.yaml

repos/
└── private-repo-using-token.yaml
```

## How to Use

### Clone the Repository

```bash
git clone https://github.com/ITBeyder/argocd-environment.git
cd argocd-environment
```

### Create or Update cluster.json

Define the K3s clusters and their ports:

```json
{
    "dev": 6444,
    "stage": 6445,
    "prod": 6446
}
```

### Run the Main Script

```bash
python main.py
```

## Access ArgoCD

Find the ArgoCD admin password in `argocd_admin_password.txt`.

Update the Local Hosts File
```
sudo vi /etc/hosts
127.0.0.1 argocd.minikube.local
```

Open your browser at: `http://argocd.minikube.local`

Default login is `admin` and the password from `argocd_admin_password.txt`.

## Cleaning Up

To stop and remove all K3s clusters:

```bash
docker rm -f $(docker ps -a -q --filter "name=k3s-")
docker volume rm $(docker volume ls -q --filter "name=k3s-")
```
