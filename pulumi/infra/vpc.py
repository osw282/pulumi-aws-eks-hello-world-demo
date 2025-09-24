import pulumi_aws as aws
from typing import Any


def create_vpc(
    name: str,
    cidr: str,
    azs: list[str],
    public_cidrs: list[str],
    private_cidrs: list[str],
    base_tags: dict[str, str]
) -> dict[str, Any]:
    """Create a VPC with public and private subnets.

    Args:
        name: The name of the VPC
        cidr: The CIDR block for the VPC
        azs: The availability zones for the subnets
        public_cidrs: The CIDR blocks for the public subnets
        private_cidrs: The CIDR blocks for the private subnets
        base_tags: The base tags for the resources

    Returns:
        A dictionary containing the VPC, Internet Gateway, Public Route Table, Public Subnets, Private Subnets, and Private Route Tables.
    """
    if len(public_cidrs) != len(private_cidrs):
        raise ValueError("publicSubnetCidrs and privateSubnetCidrs must have the same length")

    # VPC
    vpc = aws.ec2.Vpc(
        f"{name}-vpc",
        cidr_block=cidr,
        enable_dns_hostnames=True,
        enable_dns_support=True,
        tags={**base_tags, "Name": f"{name}-vpc"}
    )

    # Internet Gateway
    # Allows communication between your VPC and the internet.
    igw = aws.ec2.InternetGateway(
        f"{name}-igw",
        vpc_id=vpc.id,
        tags={**base_tags, "Name": f"{name}-igw"}
    )

    # Public route table with default route to IGW
    # A set of rules that determine where network traffic from your public subnets is directed.
    public_rt = aws.ec2.RouteTable(
        f"{name}-public-rt",
        vpc_id=vpc.id,
        routes=[aws.ec2.RouteTableRouteArgs(
            cidr_block="0.0.0.0/0",
            gateway_id=igw.id,
        )],
        tags={**base_tags, "Name": f"{name}-public-rt"}
    )

    public_subnets: list[aws.ec2.Subnet] = []
    private_subnets: list[aws.ec2.Subnet] = []
    private_rts: list[aws.ec2.RouteTable] = []

    # Per-AZ subnets and NATs
    for i, az in enumerate(azs[:len(public_cidrs)]):
        # Public subnet
        # A subnet that is connected to the internet.
        pub_subnet = aws.ec2.Subnet(
            f"{name}-public-{i+1}",
            vpc_id=vpc.id,
            cidr_block=public_cidrs[i],
            availability_zone=az,
            map_public_ip_on_launch=True,
            tags={**base_tags,
                "Name": f"{name}-public-{az}",
                # EKS uses this tag to place internet-facing LBs
                "kubernetes.io/role/elb": "1",
            },
        )
        public_subnets.append(pub_subnet)

        # Associate with public RT
        aws.ec2.RouteTableAssociation(
            f"{name}-public-rt-assoc-{i+1}",
            subnet_id=pub_subnet.id,
            route_table_id=public_rt.id,
        )

        # NAT per AZ
        # Allows worker nodes in private subnets to access the internet.
        # Static IP address for predictable outbound traffic.
        # Useful things like external services can whitelist your NAT Gateway's IP
        eip = aws.ec2.Eip(f"{name}-nat-eip-{i+1}", domain="vpc",
                          tags={**base_tags, "Name": f"{name}-nat-eip-{az}"})
        natgw = aws.ec2.NatGateway(
            f"{name}-natgw-{i+1}",
            subnet_id=pub_subnet.id,
            allocation_id=eip.id,
            tags={**base_tags, "Name": f"{name}-natgw-{az}"},
        )

        # Private subnet
        # A subnet that is not connected to the internet.
        # Where worker nodes are deployed,
        # the recommended pattern for production environments.
        priv_subnet = aws.ec2.Subnet(
            f"{name}-private-{i+1}",
            vpc_id=vpc.id,
            cidr_block=private_cidrs[i],
            availability_zone=az,
            map_public_ip_on_launch=False,
            tags={**base_tags,
                "Name": f"{name}-private-{az}",
                # EKS uses this tag for internal LBs
                "kubernetes.io/role/internal-elb": "1",
            },
        )
        private_subnets.append(priv_subnet)

        # Private route table, default route to NAT
        # A set of rules that determine where network traffic from your private subnets is directed.
        priv_rt = aws.ec2.RouteTable(
            f"{name}-private-rt-{i+1}",
            vpc_id=vpc.id,
            routes=[aws.ec2.RouteTableRouteArgs(
                cidr_block="0.0.0.0/0",
                nat_gateway_id=natgw.id,
            )],
            tags={**base_tags, "Name": f"{name}-private-rt-{az}"},
        )
        private_rts.append(priv_rt)

        aws.ec2.RouteTableAssociation(
            f"{name}-private-rt-assoc-{i+1}",
            subnet_id=priv_subnet.id,
            route_table_id=priv_rt.id,
        )

    return {
        "vpc": vpc,
        "igw": igw,
        "public_rt": public_rt,
        "public_subnets": public_subnets,
        "private_subnets": private_subnets,
        "private_rts": private_rts,
    }
