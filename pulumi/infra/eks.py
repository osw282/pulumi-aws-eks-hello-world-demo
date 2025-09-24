import pulumi
import pulumi_aws as aws
from typing import Any


def create_eks(
    name: str,
    version: str,
    public_subnets: list[aws.ec2.Subnet],
    private_subnets: list[aws.ec2.Subnet],
    cluster_role_arn: pulumi.Input[str],
    node_role_arn: pulumi.Input[str],
    instance_types: list[str],
    desired_size: int,
    min_size: int,
    max_size: int,
    base_tags: dict[str, str],
) -> dict[str, Any]:
    """Create an EKS cluster.

    Args:
        name: The name of the EKS cluster
        version: The version of the EKS cluster
        public_subnets: The public subnets
        private_subnets: The private subnets
        cluster_role_arn: The ARN of the cluster role
        node_role_arn: The ARN of the node role
        instance_types: The instance types
        desired_size: The desired size of the node group
        min_size: The minimum size of the node group
        max_size: The maximum size of the node group
        base_tags: The base tags
    """
    # Put both public and private subnets into the cluster's VPC config
    # This allows public and internal load balancers
    all_subnet_ids = [s.id for s in (public_subnets + private_subnets)]

    cluster = aws.eks.Cluster(
        name,
        role_arn=cluster_role_arn,
        version=version,
        vpc_config=aws.eks.ClusterVpcConfigArgs(
            subnet_ids=all_subnet_ids,
            # Worker nodes can reach API server via private network
            endpoint_private_access=True,
            # Set to False for maximum security (requires VPN/bastion for kubectl access)
            # Depending on your use case, you may want to set this to True
            # You can't use kubectl access without being in the VPC without a public endpoint
            # Experiment with this setting to see what works best for you
            # I recommend setting it to False for maximum security
            # But set it to true during development to save time
            endpoint_public_access=True,
        ),
        tags={**base_tags, "Name": name},
    )

    # Managed node group in private subnets
    nodegroup = aws.eks.NodeGroup(
        f"{name}-ng",
        cluster_name=cluster.name,
        node_role_arn=node_role_arn,
        # Worker nodes are not directly accessible from internet
        # They can still reach internet via NAT Gateway for pulling images
        # More secure than placing nodes in public subnets
        subnet_ids=[s.id for s in private_subnets],
        scaling_config=aws.eks.NodeGroupScalingConfigArgs(
            desired_size=desired_size,
            min_size=min_size,
            max_size=max_size,
        ),
        instance_types=instance_types,
        # Regular EC2 pricing, guaranteed availability
        capacity_type="ON_DEMAND",
        ami_type="AL2023_x86_64_STANDARD",  # change to something else like AL2023_x86_64_NVIDIA if you need GPUs
        tags=base_tags,
    )

    # After the cluster name is known, tag subnets for cluster discovery
    def tag_subnet_with_cluster(subnet: aws.ec2.Subnet, idx: int):
        """Tag a subnet with the cluster name.

        Load Balancer Controller uses these tags to find subnets.

        Public subnets: Get internet-facing load balancers.
        Private subnets: Get internal load balancers.

        Args:
            subnet: The subnet to tag
            idx: The index of the subnet
        """
        aws.ec2.Tag(
            f"{name}-subnet-cluster-tag-{idx}",
            resource_id=subnet.id,
            key=cluster.name.apply(lambda n: f"kubernetes.io/cluster/{n}"),
            value="owned",
        )

    for i, s in enumerate(public_subnets + private_subnets, start=1):
        tag_subnet_with_cluster(s, i)

    return {
        "cluster": cluster,
        "nodegroup": nodegroup,
    }
