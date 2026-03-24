# Knative + Istio + Kubeflow 엔진 배포 가이드

> 환경: Kubernetes + Knative Serving + Istio + Kubeflow  
> 네임스페이스: `aiops`

---

## 1. 구조 개요

```
외부 요청 (:31120)
    │
    ▼
istio-ingressgateway (NodePort 31120 → HTTP 80)
    ├─ istio-ingressgateway-oauth2-proxy (CUSTOM) → /api/server oauth2 인증 스킵
    ├─ istio-ingressgateway-require-jwt (DENY)    → /api/server JWT 검증 스킵
    └─ knative-engine-allow (ALLOW)               → *.aiops.sslip.io 호스트 허용
    │
    ▼
kubeflow-gateway → Knative VirtualService
    │
    ▼
aiops 네임스페이스 (mTLS STRICT)
    ├─ ns-owner-access-istio                      → Kubeflow 사용자 및 pipeline 접근 허용
    ├─ knative-engines-allow                      → istio-system → /api/server Pod 접근 허용
    └─ engines-no-auth (RequestAuthentication)    → engine Pod JWT 검증 비활성화
    │
    ▼
engine Pod → 200 OK
```

---

## 2. Knative Service 매니페스트

> ✅ 성공 기준: `engine-t1-seg` 설정을 기준으로 작성

**중요 규칙:**
- `protocol: TCP` 제거 — Istio가 HTTP로 인식하지 못해 301 리다이렉트 발생
- `name: user-container` 제거
- `traffic` 섹션 제거

```yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: engine-t1-seg
  namespace: aiops
  labels:
    app.kubernetes.io/part-of: aiops
    engine: t1-seg
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/minScale: "1"
        autoscaling.knative.dev/maxScale: "1"
        autoscaling.knative.dev/target: "1"
        autoscaling.knative.dev/scale-to-zero-pod-retention-period: "5m"
    spec:
      timeoutSeconds: 600
      containerConcurrency: 1
      imagePullSecrets:
        - name: acr-secret
      nodeSelector:
        nvidia.com/gpu.model: rtx3090
      containers:
        - image: 192.168.0.80:30002/kubeflow/engine-t1-seg:2.5.1
          ports:
            - containerPort: 9001
          resources:
            limits:
              nvidia.com/gpu: "1"
            requests:
              cpu: "2"
              memory: "8Gi"
          readinessProbe:
            httpGet:
              path: /api/server
              port: 9001
            initialDelaySeconds: 30
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /api/server
              port: 9001
            initialDelaySeconds: 60
            periodSeconds: 30
```

---

## 3. kubeflow-gateway — httpsRedirect 제거

> ⚠️ `httpsRedirect: true` 가 있으면 모든 HTTP 요청이 301로 리다이렉트됨  
> Knative VirtualService가 이 gateway를 사용하므로 반드시 제거 필요

```yaml
# kubectl edit gateway kubeflow-gateway -n kubeflow
apiVersion: networking.istio.io/v1
kind: Gateway
metadata:
  name: kubeflow-gateway
  namespace: kubeflow
spec:
  selector:
    istio: ingressgateway
  servers:
  - hosts:
    - '*'
    port:
      name: http
      number: 80
      protocol: HTTP
    # tls.httpsRedirect: true 반드시 제거
  - hosts:
    - '*'
    port:
      name: https
      number: 443
      protocol: HTTPS
    tls:
      credentialName: kubeflow-tls-cert
      mode: SIMPLE
```

---

## 4. PeerAuthentication — mTLS STRICT

> **역할:** `aiops` 네임스페이스 내 모든 Pod 간 통신을 mTLS로 강제  
> **필요성:** 네임스페이스 보안 기준선. AuthorizationPolicy들과 함께 동작하며 신뢰할 수 없는 트래픽 차단

```yaml
# peer-auth-strict.yaml
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: aiops
spec:
  mtls:
    mode: STRICT
```

---

## 5. RequestAuthentication — JWT 검증 비활성화

> **역할:** `app.kubernetes.io/part-of: aiops` 레이블을 가진 engine Pod들에 대해 JWT 토큰 검증을 하지 않도록 선언  
> **필요성:** 없으면 `istio-ingressgateway-require-jwt` DENY 정책이 engine Pod 레벨까지 JWT를 요구할 수 있음

```yaml
# engines-no-auth.yaml
apiVersion: security.istio.io/v1beta1
kind: RequestAuthentication
metadata:
  name: engines-no-auth
  namespace: aiops
spec:
  selector:
    matchLabels:
      app.kubernetes.io/part-of: aiops
  jwtRules: []
```

---

## 6. AuthorizationPolicy — oauth2-proxy 인증 스킵

> **역할:** oauth2-proxy 인증을 거치지 않아도 되는 경로 지정  
> **필요성:** `/api/server`가 없으면 oauth2-proxy가 인증을 요구하여 로그인 페이지로 리다이렉트됨  
> **적용 대상:** `istio-ingressgateway` Pod (게이트웨이 레벨)

```yaml
# istio-ingressgateway-oauth2-proxy.yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: istio-ingressgateway-oauth2-proxy
  namespace: istio-system
spec:
  action: CUSTOM
  provider:
    name: oauth2-proxy
  selector:
    matchLabels:
      app: istio-ingressgateway
  rules:
  - to:
    - operation:
        notPaths:
        - /dex/*
        - /dex/**
        - /oauth2/*
        - /api/server
        - /api/models
        - /api/models/*
        - /api/parameters
        - /api/validation
        - /api/analysis
        - /api/cancel
        - /api/cancel/*
    when:
    - key: request.headers[authorization]
      notValues:
      - '*'
```

---

## 7. AuthorizationPolicy — JWT 없는 요청 차단 예외

> **역할:** JWT 토큰이 없는 요청을 기본 차단하되, 특정 경로는 예외 처리  
> **필요성:** `/api/server`가 notPaths에 없으면 JWT 없는 curl 요청이 차단됨  
> **적용 대상:** `istio-ingressgateway` Pod (게이트웨이 레벨)

```yaml
# istio-ingressgateway-require-jwt.yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: istio-ingressgateway-require-jwt
  namespace: istio-system
spec:
  action: DENY
  selector:
    matchLabels:
      app: istio-ingressgateway
  rules:
  - from:
    - source:
        notRequestPrincipals:
        - '*'
    to:
    - operation:
        notPaths:
        - /dex/*
        - /dex/**
        - /oauth2/*
        - /api/server
        - /api/models
        - /api/models/*
        - /api/parameters
        - /api/validation
        - /api/analysis
        - /api/cancel
        - /api/cancel/*
```

---

## 8. AuthorizationPolicy — 게이트웨이 레벨 호스트 허용

> **역할:** `*.aiops.sslip.io` 호스트로 들어오는 요청을 ingressgateway에서 허용  
> **필요성:** 없으면 Knative 서비스 호스트가 게이트웨이에서 차단됨  
> **주의:** 포트 포함 패턴(`*.aiops.sslip.io:*`)도 반드시 추가 — curl 요청 시 Host 헤더에 포트가 포함되기 때문

```yaml
# knative-engine-allow.yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: knative-engine-allow
  namespace: istio-system
spec:
  action: ALLOW
  selector:
    matchLabels:
      app: istio-ingressgateway
  rules:
  - to:
    - operation:
        hosts:
        - '*.aiops.192.168.0.80.sslip.io'
        - '*.aiops.192.168.0.80.sslip.io:*'
```

---

## 9. AuthorizationPolicy — Kubeflow 사용자 및 pipeline 접근 허용

> **역할:** Kubeflow 대시보드/notebook에서 aiops 네임스페이스 리소스 접근 허용  
> **필요성:** Kubeflow UI 및 ml-pipeline에서 aiops 네임스페이스 접근 시 필요  
> **적용 대상:** `aiops` 네임스페이스 전체 (Pod 레벨)

```yaml
# ns-owner-access-istio.yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: ns-owner-access-istio
  namespace: aiops
  annotations:
    role: admin
    user: aiops@neurophet.com
spec:
  rules:
  - from:
    - source:
        principals:
        - cluster.local/ns/istio-system/sa/istio-ingressgateway-service-account
        - cluster.local/ns/kubeflow/sa/ml-pipeline-ui
    when:
    - key: request.headers[kubeflow-userid]
      values:
      - aiops@neurophet.com
  - when:
    - key: source.namespace
      values:
      - aiops
  - to:
    - operation:
        paths:
        - /healthz
        - /metrics
        - /wait-for-drain
  - from:
    - source:
        principals:
        - cluster.local/ns/kubeflow/sa/notebook-controller-service-account
    to:
    - operation:
        methods:
        - GET
        paths:
        - '*/api/kernels'
  - from:
    - source:
        namespaces:
        - istio-system
    to:
    - operation:
        paths:
        - /api/server
        - /api/server/*
        - /api/*
```

---

## 10. AuthorizationPolicy — Pod 레벨 엔진 접근 허용

> **역할:** `istio-system`, `aiops`, `knative-serving`에서 오는 `/api/server` 요청을 Pod 레벨에서 허용  
> **필요성:** 게이트웨이를 통과해도 Pod 레벨에서 차단됨 (403 RBAC)  
> **주의:** `from`과 `to`를 반드시 같은 `rule` 안에 작성해야 AND 조건으로 동작

```yaml
# knative-engines-allow.yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: knative-engines-allow
  namespace: aiops
spec:
  rules:
  - from:
    - source:
        namespaces:
        - istio-system
        - aiops
        - knative-serving
    to:
    - operation:
        paths:
        - /api/server
        - /api/models
        - /api/models/*
        - /api/parameters
        - /api/validation
        - /api/analysis
        - /api/cancel
        - /api/cancel/*
        - /healthz
        - /metrics
        - /wait-for-drain
```

---

## 11. 배포 후 검증

```bash
# 서비스 상태 확인
kubectl get ksvc -n aiops

# Pod 상태 확인
kubectl get pods -n aiops

# API 접속 테스트
curl http://engine-t1-seg.aiops.192.168.0.80.sslip.io:31120/api/server
curl http://engine-flair-seg.aiops.192.168.0.80.sslip.io:31120/api/server
curl http://engine-normative.aiops.192.168.0.80.sslip.io:31120/api/server
```

---

## 12. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| HTTP 301 리다이렉트 | `kubeflow-gateway`의 `httpsRedirect: true` | tls 블록 제거 |
| RBAC: access denied (403) | `knative-engines-allow`에 `/api/server` 경로 누락 또는 from+to 분리 작성 | from+to 같은 rule로 수정 및 경로 추가 |
| Empty reply / 응답 없음 | `knative-engine-allow` 호스트 패턴에 포트 누락 | `*.sslip.io:*` 패턴 추가 |
| SSL wrong version number | HTTP 포트에 HTTPS 요청 시도 | 포트 번호 확인 (HTTP: 31120, HTTPS: 32392) |
| oauth2 로그인 페이지로 리다이렉트 | `istio-ingressgateway-oauth2-proxy`에 `/api/server` 누락 | notPaths에 `/api/server` 추가 |