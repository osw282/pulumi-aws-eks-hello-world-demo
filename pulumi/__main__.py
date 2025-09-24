import pulumi
import pulumi_aws as aws

from infra.vpc import create_vpc
from infra.iam import create_eks_roles
from infra.eks import create_eks
from infra.ecr import create_ecr_repository
from infra.alb_controller.alb_controller import create_alb_controller

config = pulumi.Config()
proj_name = config.get("name")
region = aws.config.region

eks_version = config.get("eksVersion") or "1.33" # 1.33 is the latest version as of 2025-09-24
vpc_cidr = config.get("vpcCidr") or "10.0.0.0/16" # 10.0.0.0/16 is a common VPC CIDR block, first 16 bits are fixed
public_cidrs = config.get_object("publicSubnetCidrs") or ["10.0.1.0/24", "10.0.2.0/24"] 
private_cidrs = config.get_object("privateSubnetCidrs") or ["10.0.3.0/24", "10.0.4.0/24"]
instance_types = config.get_object("instanceTypes") or ["t3.medium"]
desired_size = int(config.get("desiredSize") or 2)
min_size = int(config.get("minSize") or 2)
max_size = int(config.get("maxSize") or 4)

base_tags = {
    "Project": proj_name,
    "pulumi:stack": pulumi.get_stack(),
}

# Choose AZs automatically
azs = aws.get_availability_zones(state="available").names[:len(public_cidrs)]

# Network
net = create_vpc(
    name=proj_name,
    cidr=vpc_cidr,
    azs=azs,
    public_cidrs=public_cidrs,
    private_cidrs=private_cidrs,
    base_tags=base_tags,
)

# IAM
roles = create_eks_roles(proj_name, base_tags)

# EKS
eks_resources = create_eks(
    name=proj_name,
    version=eks_version,
    public_subnets=net["public_subnets"],
    private_subnets=net["private_subnets"],
    cluster_role_arn=roles["cluster_role"].arn,
    node_role_arn=roles["node_role"].arn,
    instance_types=instance_types,
    desired_size=desired_size,
    min_size=min_size,
    max_size=max_size,
    base_tags=base_tags,
)

cluster = eks_resources["cluster"]

# Generate kubeconfig
# At the moment, this is the only way to get the kubeconfig for the cluster
# This is because the cluster.kubeconfig attribute is not available in the newer provider versions
kubeconfig = pulumi.Output.all(cluster.endpoint, cluster.certificate_authority, cluster.name).apply(
    lambda args: f"""apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: {args[1]['data']}
    server: {args[0]}
  name: {args[2]}
contexts:
- context:
    cluster: {args[2]}
    user: {args[2]}
  name: {args[2]}
current-context: {args[2]}
kind: Config
preferences: {{}}
users:
- name: {args[2]}
  user:
    exec:
      apiVersion: client.authentication.k8s.io/v1beta1
      command: aws
      args:
      - eks
      - get-token
      - --cluster-name
      - {args[2]}
"""
)

# AWS Load Balancer Controller
alb_controller_resources = create_alb_controller(
    name=proj_name,
    cluster=cluster,
    kubeconfig=kubeconfig,
    vpc_id=net["vpc"].id,
    base_tags=base_tags,
)

# ECR Repository
ecr_resources = create_ecr_repository(proj_name, base_tags)

# Handy outputs
# Useful for debugging
# You don't need to export these if you don't need them
pulumi.export("region", region)
pulumi.export("clusterName", cluster.name)
pulumi.export("clusterEndpoint", cluster.endpoint)
pulumi.export("kubeconfig", kubeconfig)
pulumi.export("vpcId", net["vpc"].id)
pulumi.export("ecrRepositoryUrl", ecr_resources["repository"].repository_url)
pulumi.export("publicSubnetIds", [s.id for s in net["public_subnets"]])
pulumi.export("privateSubnetIds", [s.id for s in net["private_subnets"]])
pulumi.export("oidcProviderArn", alb_controller_resources["oidc_provider"].arn)
pulumi.export("albControllerRoleArn", alb_controller_resources["role"].arn)

# To configure kubectl, run:
# aws eks update-kubeconfig --region <region> --name <cluster-name>
