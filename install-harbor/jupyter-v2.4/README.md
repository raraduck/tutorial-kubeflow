# Buildah tutorial
## How to build
```bash
buildah bud \
  -t 192.168.0.80:30002/kubeflow/jupyter-v2.4:0 \
  .
```
## How to login
```bash
buildah --tls-verify=false login -u admin
# password:H*****123***
```
## How to push
```bash
buildah --tls-verify=false push 192.168.0.80:30002/kubeflow/jupyter-v2.4:0
```