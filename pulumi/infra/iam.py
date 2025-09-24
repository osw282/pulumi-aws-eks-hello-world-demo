import json
import pulumi_aws as aws
from typing import Any


def create_eks_roles(
    name: str, 
    base_tags: dict[str, str]
) -> dict[str, Any]:
    """Create EKS roles.

    Args:
        name: The name of the EKS cluster
        base_tags: The base tags for the resources

    Returns:
        A dictionary containing the cluster role and node role.
    """
    # Cluster role
    # only the AWS EKS service can "assume" (use) this role
    cluster_assume = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "eks.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }

    cluster_role = aws.iam.Role(
        f"{name}-cluster-role",
        assume_role_policy=json.dumps(cluster_assume),
        tags={**base_tags, "Name": f"{name}-cluster-role"},
    )

    aws.iam.RolePolicyAttachment(
        f"{name}-cluster-policy",
        role=cluster_role.name,
        # allows the cluster to manage AWS resources
        # e.g. security groups and load balancers, etc.
        policy_arn="arn:aws:iam::aws:policy/AmazonEKSClusterPolicy",
    )

    # Node group role
    # only the AWS EC2 service can "assume" (use) this role
    node_assume = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "ec2.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }

    node_role = aws.iam.Role(
        f"{name}-node-role",
        assume_role_policy=json.dumps(node_assume),
        tags={**base_tags, "Name": f"{name}-node-role"},
    )

    # Worker node policies
    aws.iam.RolePolicyAttachment(
        f"{name}-worker-node-policy",
        role=node_role.name,
        # allows the node to connect to the EKS cluster
        # register the node with the EKS cluster
        # receive work from the control plane
        policy_arn="arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
    )
    
    # allow the node to assign IP addresses to pods from VPC subnets
    aws.iam.RolePolicyAttachment(
        f"{name}-cni-policy",
        role=node_role.name,
        policy_arn="arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
    )

    # allow the node to pull images from the ECR
    aws.iam.RolePolicyAttachment(
        f"{name}-ecr-ro",
        role=node_role.name,
        policy_arn="arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
    )

    return {
        "cluster_role": cluster_role,
        "node_role": node_role,
    }
