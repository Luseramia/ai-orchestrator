pipeline {
    agent {
        kubernetes {
            yaml '''
apiVersion: v1
kind: Pod
metadata:
  annotations:
    vault.hashicorp.com/agent-inject: "true"
    vault.hashicorp.com/role: "kaniko"
spec:
  serviceAccountName: kaniko
  containers:
    - name: kaniko
      image: gcr.io/kaniko-project/executor:debug
      command: ["sleep"]
      args: ["99d"]
      tty: true
      volumeMounts:
        - name: ci-workspace
          mountPath: /ci-workspace
        - name: docker-config
          mountPath: /kaniko/.docker
    - name: helper
      image: alpine/git:latest
      command: ["sleep"]
      args: ["99d"]
      tty: true
      volumeMounts:
        - name: ci-workspace
          mountPath: /ci-workspace
    - name: python
      image: python:3.13-slim-bookworm
      command: ["sleep"]
      args: ["99d"]
      tty: true
      volumeMounts:
        - name: ci-workspace
          mountPath: /ci-workspace
  volumes:
    - name: ci-workspace
      emptyDir: {}
    - name: docker-config
      emptyDir: {}
'''
        }
    }

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timestamps()
    }

    environment {
        APP_REPO = 'git@github.com:Luseramia/ai-orchestrator.git'
        DEPLOY_REPO = 'git@github.com:Luseramia/k8s-project-helm.git'
        GIT_BRANCH = 'main'
        DEPLOY_DIR = 'ai-orchestrator'
        REGISTRY = 'registry.registry.svc.cluster.local:5000'
        IMAGE_NAME = 'ai-orchestrator'
        TAG = "${BUILD_NUMBER}"
        PYTHONDONTWRITEBYTECODE = '1'
        PYTHONUNBUFFERED = '1'
    }

    stages {
        stage('Checkout application and deployment') {
            steps {
                container('helper') {
                    withCredentials([sshUserPrivateKey(credentialsId: 'github_key', keyFileVariable: 'KEY')]) {
                        sh '''
                            set -eu
                            mkdir -p "$HOME/.ssh"
                            chmod 700 "$HOME/.ssh"
                            ssh-keyscan -p 443 ssh.github.com > "$HOME/.ssh/known_hosts" 2>/dev/null
                            chmod 600 "$HOME/.ssh/known_hosts"
                            export GIT_SSH_COMMAND="ssh -i '$KEY' -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o HostName=ssh.github.com -p 443"

                            # Shared checkout paths are separate from the image's /app.
                            git config --global --add safe.directory /ci-workspace/source
                            git config --global --add safe.directory /ci-workspace/deploy
                            git clone --branch "$GIT_BRANCH" --single-branch "$APP_REPO" /ci-workspace/source
                            git clone --branch "$GIT_BRANCH" --single-branch "$DEPLOY_REPO" /ci-workspace/deploy
                            test -f /ci-workspace/source/Dockerfile
                            test -f "/ci-workspace/deploy/$DEPLOY_DIR/deployment.yaml"
                            git -C /ci-workspace/source rev-parse HEAD
                        '''
                    }
                }
            }
        }

        stage('Test application') {
            steps {
                container('python') {
                    sh '''
                        set -eu
                        cd /ci-workspace/source
                        python -m venv /tmp/orchestrator-ci-venv
                        /tmp/orchestrator-ci-venv/bin/python -m pip install --disable-pip-version-check --no-cache-dir -r requirements.txt
                        /tmp/orchestrator-ci-venv/bin/python -m pip check
                        /tmp/orchestrator-ci-venv/bin/python -m unittest discover -s tests -p test_codex_adapter.py -v
                        /tmp/orchestrator-ci-venv/bin/python -c "from fastapi.testclient import TestClient; from app.main import app; response = TestClient(app).get('/health'); assert response.status_code == 200; assert response.json()['service'] == 'ai-orchestrator'"
                    '''
                }
            }
        }

        stage('Build and push image') {
            steps {
                container('kaniko') {
                    sh '''
                        set -eu
                        /kaniko/executor \
                            --context=/ci-workspace/source \
                            --dockerfile=/ci-workspace/source/Dockerfile \
                            --destination="$REGISTRY/$IMAGE_NAME:$TAG" \
                            --insecure \
                            --skip-tls-verify \
                            --cache=true
                    '''
                }
            }
        }

        stage('Update deployment in Git') {
            steps {
                container('helper') {
                    withCredentials([sshUserPrivateKey(credentialsId: 'github_key', keyFileVariable: 'KEY')]) {
                        sh '''
                            set -eu
                            cd /ci-workspace/deploy
                            git config --global --add safe.directory /ci-workspace/deploy
                            export GIT_SSH_COMMAND="ssh -i '$KEY' -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o HostName=ssh.github.com -p 443"
                            # Other Jenkins jobs also update this repository.
                            git pull --ff-only origin "$GIT_BRANCH"
                            export DEPLOYMENT_FILE="$DEPLOY_DIR/deployment.yaml"
                            export NEW_IMAGE="$REGISTRY/$IMAGE_NAME:$TAG"
                            /bin/sh /ci-workspace/source/scripts/update-deployment-image.sh
                            git diff --check
                            git diff -- "$DEPLOYMENT_FILE"
                            git config user.name 'Jenkins CI'
                            git config user.email 'jenkins@ci.local'
                            git add -- "$DEPLOYMENT_FILE"
                            if git diff --cached --quiet; then
                                echo 'Deployment already references this image.'
                            else
                                git commit -m "Deploy $IMAGE_NAME:$TAG [skip ci]"
                                git push origin "$GIT_BRANCH"
                            fi
                        '''
                    }
                }
            }
        }
    }

    post {
        success {
            echo "Published ${env.REGISTRY}/${env.IMAGE_NAME}:${env.TAG}. Argo CD application ai-orchestrator will sync the updated Git revision."
        }
    }
}
