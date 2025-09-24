import pulumi_aws as aws
from typing import Any


def create_ecr_repository(
    name: str,
    base_tags: dict[str, str]
) -> dict[str, Any]:
    """
    Creates an ECR repository for container images.
    
    Args:
        name: The name of the ECR repository
        base_tags: Base tags to apply to all resources
    
    Returns:
        Dictionary containing the ECR repository resource
    """
    
    # ECR Repository for container images
    repository = aws.ecr.Repository(
        f"{name}-ecr",
        name=f"{name}-hello-world",
        image_tag_mutability="MUTABLE",
        image_scanning_configuration=aws.ecr.RepositoryImageScanningConfigurationArgs(
            scan_on_push=True,
        ),
        encryption_configurations=[{
            "encryption_type": "AES256",
        }],
        tags={**base_tags, "Name": f"{name}-hello-world"},
    )

    # Lifecycle policy to manage image retention
    # This is just a sample policy, you can change it to your needs
    lifecycle_policy = aws.ecr.LifecyclePolicy(
        f"{name}-ecr-lifecycle-policy",
        repository=repository.name,
        policy="""{
            "rules": [
                {
                    "rulePriority": 1,
                    "description": "Keep last 10 images",
                    "selection": {
                        "tagStatus": "tagged",
                        "tagPrefixList": ["v"],
                        "countType": "imageCountMoreThan",
                        "countNumber": 10
                    },
                    "action": {
                        "type": "expire"
                    }
                },
                {
                    "rulePriority": 2,
                    "description": "Delete untagged images older than 1 day",
                    "selection": {
                        "tagStatus": "untagged",
                        "countType": "sinceImagePushed",
                        "countUnit": "days",
                        "countNumber": 1
                    },
                    "action": {
                        "type": "expire"
                    }
                }
            ]
        }""",
    )
    
    return {
        "repository": repository,
        "lifecycle_policy": lifecycle_policy,
    }
