# pulumi-aws-eks-hello-world-demo

A demo project showing how to provision an Amazon EKS cluster on AWS using Pulumi, with a VPC, subnets, IAM roles, and the AWS Load Balancer Controller. Includes a simple "Hello World" Kubernetes application exposed via Gateway API and Kong Gateway.

This demo aims to give you a step-by-step, hand-holding guide you can follow.

## What we are going to do
![system](imgs/system.png)


# Prerequisites

- [Pulumi](https://www.pulumi.com/)
- [uv](https://docs.astral.sh/uv/)
- [Docker](https://www.docker.com/)
- [kubectl](https://kubernetes.io/docs/reference/kubectl/)

# Getting Started

```bash
uv sync
source .venv/bin/activate
```

# AWS

Configure your AWS credentials.

You can configure this any way you like as long as you know which profile has access.

Export the profile:

```bash
export AWS_PROFILE="<YOUR_PROFILE_NAME>"
```

Verify your identity:

```bash
aws sts get-caller-identity --profile <profile name>
```

You should see something like:
```bash
{
    "UserId": "BXO3165...ZP36NYY5FOU:my-session",
    "Account": "9263...9123",
    "Arn": "arn:aws:sts::9263...9123:assumed-role/.../my-session"
}
```

Set your profile for Pulumi here: [pulumi/Pulumi.dev.yaml](pulumi/Pulumi.dev.yaml)


# Pulumi
After setting your aws profile for Pulumi.

```bash
cd pulumi
pulumi login
pulumi stack init dev
pulumi up
```

You should see progress in your CLI.

You can also view the online dashboard. It is quite good compared to some other IaC tools. You can track stack updates and see a graph showing relationships between resources.

Standing up the infra takes around 10-15 minutes.

Once finished, you should see an AWS cluster named `my-eks-cluster-*` in the AWS console.

You might need to manually configure your kubeconfig to access the cluster. Run:
```bash
aws eks update-kubeconfig --region <region> --name <cluster-name> --profile <profile>
```

To quickly check you have access locally, run:

```bash
kubectl get pod
```

You should see `No resources found in default namespace.` since we have not deployed anything yet.

# Deploying Our Hello World App

I have made a very simple hello world app in the [src](src) folder. It is a single page web app that just says hello world, served by a Flask server.

Nothing special there. Feel free to poke around.

You can try running it locally.

From the project root, run:

```bash
python src/app.py
```

You should see:

![run_app_local.png](imgs/run_app_local.png)

Now try in your browser: [http://localhost:5000/ui](http://localhost:5000/ui)

You should see:

![ui_local](imgs/ui_local.png)

Cool, let's build a Docker image and push it to ECR.

## Building And Pushing To ECR

There should be an ECR repository named `my-eks-cluster-hello-world`. You can find it in the AWS console.

![ecr](imgs/ecr.png)

There is a [Dockerfile](Dockerfile) you can use to build the app image.

First, authenticate Docker to your ECR.

Inside the `pulumi` folder, run (set your region and profile):
```bash
aws ecr get-login-password --region <your-region> --profile <your-profile-name> | docker login --username AWS --password-stdin $(pulumi stack output ecrRepositoryUrl | cut -d'/' -f1)
```
You should see `Login Succeeded`.

Next, build and push the image to ECR.

Still inside the `pulumi` folder, run:

```bash
docker buildx build --platform linux/amd64 -t $(pulumi stack output ecrRepositoryUrl) .. --push
```

You should see the image with the `latest` tag in ECR afterwards.

## Deploy The App On Our Cluster

In [k8s/hello_world](k8s/hello_world/) you will find three files: [deployment.yaml](k8s/hello_world/deployment.yaml), [service.yaml](k8s/hello_world/service.yaml), and [http_route.yaml](k8s/hello_world/http_route.yaml). Ignore `http_route.yaml` for now.

In [deployment.yaml](k8s/hello_world/deployment.yaml) we define the Pod. Set the image URI to the one from ECR.

![images_uri](imgs/images_uri.png)

Copy and paste the URI into [line 17](k8s/hello_world/deployment.yaml#17) in `deployment.yaml`.

`service.yaml` defines the internal service (ClusterIP) for the hello world deployment.

When you are ready to deploy, from the project root run:

```bash
kubectl apply -f k8s/hello_world/deployment.yaml -f k8s/hello_world/service.yaml
```

To view the deployment and service, run:

```bash
kubectl get pods
```

You should see two replicas of the deployment.

![get_pod](imgs/get_pod.png)

Do the same for the service:

```bash
kubectl get svc
```

You should see an internal service of type ClusterIP for the hello world deployment.

![get_svc](imgs/get_svc.png)

Let's port-forward to quickly verify the app. If you look at [pulumi/infra/eks.py](pulumi/infra/eks.py#52), `endpoint_public_access` is set to `True`, so we can use `kubectl port-forward`. If it is `False`, you would need a way to be inside the VPC first.

Since we enabled `endpoint_public_access`, port-forward:
```bash
kubectl port-forward svc/hello-world-app-service 5000:5000
```

![port-forward](imgs/port_forward.png)

You should be able to reach [http://localhost:5000/ui](http://localhost:5000/ui) and see the same UI as earlier.

Cool, everything is working as expected. You can stop the port-forward.

What if we want to expose it to the internet over HTTP or HTTPS?

# Exposing Our Service To The Internet

There are many ways to do this, for example using Kubernetes Ingress or Gateway API.

We will go with Gateway API in this demo. Gateway API is a newer Kubernetes API for traffic routing. It is more expressive and extensible than Ingress.

At the time this demo was created, [Kubernetes Ingress](https://kubernetes.io/docs/concepts/services-networking/ingress/) was at v1.19 and frozen.

You will want to learn more about [Kubernetes Gateway API](https://kubernetes.io/docs/concepts/services-networking/gateway/) sooner or later.

I will not spend too much time explaining Gateway API and all the components here. If you are interested, check out my [k8s-gateway-api-demo](https://github.com/osw282/k8s-gateway-api-demo).

We will use the [Kong Gateway Operator](https://developer.konghq.com/operator/dataplanes/get-started/kic/install/) as the GatewayClass implementation.

## Deploying Gateway API

Inside [k8s/gateway_api/](k8s/gateway_api/) you will find these manifests.

Gateway API requires a minimum of three resources:
- [GatewayClass](k8s/gateway_api/gateway_class.yaml)
- [Gateway](k8s/gateway_api/gateway.yaml)
- [HTTPRoute](k8s/hello_world/http_route.yaml) or a `GRPCRoute`

We also have three additional manifests that will help us set up Gateway API:
- [k8s/gateway_api/namespace.yaml](k8s/gateway_api/namespace.yaml)
- [k8s/gateway_api/gateway_config.yaml](k8s/gateway_api/gateway_config.yaml)
- [k8s/gateway_api/reference_grant.yaml](k8s/gateway_api/reference_grant.yaml)

I have explained what each of these does and why they are here in my [k8s-gateway-api-demo](https://github.com/osw282/k8s-gateway-api-demo) repo.

Let's apply them from the project root.

### 1. Install Kong Gateway Operator with Ingress Controller

I recommend visiting Kong's getting started page and following their instructions:

[Install Kong Gateway Operator with Kong Ingress Controller](https://developer.konghq.com/operator/dataplanes/get-started/kic/install/)

If you prefer, copy the commands below. They install the latest version as of 25-Sep-2025 of Kong Gateway Operator:
```bash
# Install Gateway API CRDs
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.3.0/standard-install.yaml

# Install Kong Gateway Operator using Helm
helm repo add kong https://charts.konghq.com
helm repo update

helm upgrade --install kgo kong/gateway-operator -n kong-system --create-namespace \
  --set image.tag=1.6.1 \
  --set kubernetes-configuration-crds.enabled=true \
  --set env.ENABLE_CONTROLLER_KONNECT=true

# Wait for Kong Gateway Operator to be ready
kubectl -n kong-system wait --for=condition=Available=true --timeout=120s deployment/kgo-gateway-operator-controller-manager
```

Check status:
```bash
kubectl get pods -n kong-system
```

You should see:
![kong_operator.png](imgs/kong_operator.png)

### 2. Create a namespace for Kong

```bash
kubectl apply -f k8s/gateway_api/namespace.yaml
```

### 3. Create configuration for Kong's data plane and control plane

```bash
kubectl apply -f k8s/gateway_api/gateway_config.yaml
```

### 4. Create the Kong GatewayClass

```bash
kubectl apply -f k8s/gateway_api/gateway_class.yaml
```

### 5. Create the Gateway

```bash
kubectl apply -f k8s/gateway_api/gateway.yaml
```

### 6. Create a ReferenceGrant

```bash
kubectl apply -f k8s/gateway_api/reference_grant.yaml
```

To check if Kong's data and control planes are running, wait for them to be ready:

```bash
kubectl get pods -n kong
```

![kong_planes](imgs/kong_planes.png)

By now we should have an external IP address. Verify by running:

```bash
kubectl get svc -n kong
```

![kong_svc](imgs/kong_svc.png)

You should see an external IP associated with Kong's LoadBalancer service.

Also visit the Load Balancer page in the AWS console.

![load_balancer](imgs/load_balacner.png)

Wait for it to provision. The state should become "Active".

Now we should be able to reach the app via the external IP.

## Create an HTTPRoute for the hello world app

Now that Kong is set up with Gateway API, define a route for the hello world deployment.

From the project root, run:

```bash
kubectl apply -f k8s/hello_world/http_route.yaml
```

To check that it was created successfully:

```bash
kubectl get httproute -n kong
```

You should see:

![http_route](imgs/http_route.png)

Print the full URL to reach the app:

```bash
echo "http://$(kubectl get svc -n kong -o jsonpath='{.items[?(@.spec.type=="LoadBalancer")].status.loadBalancer.ingress[0].hostname}')/ui"
```

We did it.

![success](imgs/great_success.png)

We have a publicly reachable app.

I hope you find this demo useful.

# What's Next

## HTTPS

There are two ways to set up HTTPS with Kong.

If you remember, in [k8s/gateway_api/gateway_config.yaml](k8s/gateway_api/gateway_config.yaml), Kong can use either an NLB or a CLB. CLB is outdated and should not be used any more, so we went with an internet-facing NLB.

But NLB is layer 4. It supports TCP but not HTTP or HTTPS. So what do we do?

### Let Kong do the work and keep the NLB in front

Even if Kong is fronted by an NLB, you can still reach your services over HTTPS because:
- The NLB is just passing raw TCP (port 443) to Kong.
- Kong terminates the TLS connection using the certificate you configure.
- From the browser’s perspective, it is still a normal HTTPS endpoint.

The flow looks like this:

```bash
Browser (HTTPS request on port 443)
    ↓
AWS NLB (forwards TCP:443, no TLS termination)
    ↓
Kong Gateway (terminates TLS using cert from K8s Secret)
    ↓
Backend Service
```

As long as Kong is configured with a valid cert (self-signed, Let’s Encrypt via cert-manager, or one you upload), your browser will connect via HTTPS with no issue.

Whichever way you choose to get a TLS certificate is up to you, but you will need a domain.

### Put an ALB in front of Kong

If you put an ALB in front, the ALB can terminate TLS (certs live in ACM) and Kong will see plain HTTP.

That means Kong does not need to expose a public-facing LoadBalancer.

With ALB:

- The ALB becomes the external entrypoint.
- ALB terminates TLS and forwards plain HTTP to Kong.
- Kong only needs to be reachable inside the cluster, so ClusterIP is enough.
- You can set this via annotation in [k8s/gateway_api/gateway_config.yaml](k8s/gateway_api/gateway_config.yaml)

This is a common design where teams want AWS-native TLS and WAF at the edge while keeping Kong as the API gateway inside.

My recommendation is to start simple and add services as required.

# Clean Up

Remove all hello world and Kong resources from the cluster:

```bash
kubectl delete -f k8s/hello_world -f k8s/gateway_api
```

NOTE: Deleting Kong's data plane and control plane does not delete the NLB it created. You will have to either delete the LoadBalancer Service using kubectl or manually delete it in the AWS console.

If you do not, `pulumi destroy` will fail because the NLB creates ENIs in the public subnet and the subnet cannot be deleted with an ENI attached.

```bash
kubectl delete svc -n kong -l konghq.com/service
```

To bring down the cluster, run:
```bash
pulumi destroy
```

Final note: for production, I would lean toward managing an ALB or NLB yourself in Pulumi. That way:
- Pulumi manages lifecycle.
- No orphaned AWS resources.
- You still point Kong’s proxy Service at your managed ALB.

If you are going to use HTTPS and WAF, you should go with an ALB.