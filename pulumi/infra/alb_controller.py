"""Create AWS Load Balancer Controller for EKS.

If we want to use ALB instead of Classic load balancer, we need to install the AWS Load Balancer Controller.

This is a modern approach to create the AWS Load Balancer Controller for EKS.

We install it using Helm.
"""

import json
import pulumi
import pulumi_aws as aws
import pulumi_kubernetes as k8s
from typing import Any

from .alb_controller_policy import get_alb_controller_policy


def create_alb_controller(
    name: str,
    cluster: aws.eks.Cluster,
    kubeconfig: pulumi.Output[str],
    vpc_id: pulumi.Input[str],
    base_tags: dict[str, str],
) -> dict[str, Any]:
    """Create AWS Load Balancer Controller for EKS.

    Args:
        name: The name prefix for resources
        cluster: The EKS cluster
        kubeconfig: The kubeconfig for the cluster
        vpc_id: The VPC ID where the cluster is deployed
        base_tags: The base tags for resources

    Returns:
        A dictionary containing the ALB controller resources.
    """
    
    # Create OIDC Identity Provider for the EKS cluster
    # This is required for IRSA (IAM Roles for Service Accounts) to work
    # An OIDC Identity Provider allows external identity providers (like our EKS cluster) to assume AWS IAM roles.
    oidc_provider = aws.iam.OpenIdConnectProvider(
        f"{name}-oidc-provider",
        url=cluster.identities[0].oidcs[0].issuer,
        client_id_lists=["sts.amazonaws.com"],
        thumbprint_lists=[
            # EKS OIDC root CA thumbprint for eu-west-2 region (SHA-1, 40 chars)
            # Retrieved using get_oidc_root_ca_thumbprint.sh - current as of SEP 2025
            "06B25927C42A721631C1EFD9431E648FA62E1E39"
        ],
        tags={**base_tags, "Name": f"{name}-oidc-provider"},
    )
    
    # Creates dedicated IAM role with OIDC trust relationship
    # Modern approach instead of attaching policy to node role
    # Follows principle of least privilege
    alb_controller_assume_role = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {
                "Federated": oidc_provider.arn
            },
            "Action": "sts:AssumeRoleWithWebIdentity",
            "Condition": {
                "StringEquals": {
                    cluster.identities[0].oidcs[0].issuer.apply(
                        lambda issuer: f"{issuer.replace('https://', '')}:sub"
                    ): "system:serviceaccount:kube-system:aws-load-balancer-controller",
                    cluster.identities[0].oidcs[0].issuer.apply(
                        lambda issuer: f"{issuer.replace('https://', '')}:aud"
                    ): "sts.amazonaws.com"
                }
            }
        }]
    }

    # The role is only used by the AWS Load Balancer Controller service account
    alb_controller_role = aws.iam.Role(
        f"{name}-alb-controller-role",
        assume_role_policy=pulumi.Output.from_input(alb_controller_assume_role).apply(json.dumps),
        tags={**base_tags, "Name": f"{name}-alb-controller-role"},
    )

    # Create IAM policy for AWS Load Balancer Controller
    alb_controller_policy_doc = get_alb_controller_policy()

    alb_controller_policy = aws.iam.Policy(
        f"{name}-alb-controller-policy",
        policy=json.dumps(alb_controller_policy_doc),
        tags={**base_tags, "Name": f"{name}-alb-controller-policy"},
    )

    aws.iam.RolePolicyAttachment(
        f"{name}-alb-controller-policy-attachment",
        role=alb_controller_role.name,
        policy_arn=alb_controller_policy.arn,
    )

    # Create Kubernetes provider
    k8s_provider = k8s.Provider(
        f"{name}-k8s-provider",
        kubeconfig=kubeconfig,
    )

    # Create service account for AWS Load Balancer Controller
    alb_controller_sa = k8s.core.v1.ServiceAccount(
        "aws-load-balancer-controller", # must match the trust policy condition
        metadata=k8s.meta.v1.ObjectMetaArgs(
            name="aws-load-balancer-controller",
            namespace="kube-system",
            annotations={
                "eks.amazonaws.com/role-arn": alb_controller_role.arn,
            }, # this tells eks whenever a pod runs with this ServiceAccount, give it temporary AWS credentials from the IAM Role alb_controller_role.”
        ),
        opts=pulumi.ResourceOptions(provider=k8s_provider),
    )
    # For more information, you should look up IRSA, it replaces the old way of giving controllers AWS access via node instance roles.

    # Install AWS Load Balancer Controller using Helm
    alb_controller_chart = k8s.helm.v3.Chart(
        "aws-load-balancer-controller",
        k8s.helm.v3.ChartOpts(
            chart="aws-load-balancer-controller",
            version="1.13.4",  # Use latest stable version
            namespace="kube-system",
            fetch_opts=k8s.helm.v3.FetchOpts(
                repo="https://aws.github.io/eks-charts"
            ),
            values={
                "clusterName": cluster.name,
                "serviceAccount": {
                    "create": False,
                    "name": "aws-load-balancer-controller",
                },
                "region": aws.get_region().region,
                "vpcId": vpc_id,
                "podDisruptionBudget": {
                    "maxUnavailable": 1,
                },
            },
        ),
        opts=pulumi.ResourceOptions(
            provider=k8s_provider,
            depends_on=[alb_controller_sa],
        ),
    )

    return {
        "oidc_provider": oidc_provider,
        "role": alb_controller_role,
        "policy": alb_controller_policy,
        "service_account": alb_controller_sa,
        "chart": alb_controller_chart,
    }
