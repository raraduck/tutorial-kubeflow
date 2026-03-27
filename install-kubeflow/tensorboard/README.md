# Update Tensorboard Version

## 1. Color Customizing Function (>2.11)

```bash
kubectl patch configmap tensorboard-controller-config-7hd244gf2d \
  -n kubeflow \
  --type merge \
  -p '{"data":{"TENSORBOARD_IMAGE":"tensorflow/tensorflow:2.13.0"}}'
```

