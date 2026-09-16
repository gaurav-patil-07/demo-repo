pipeline {

    agent any

    stages {

        stage('Checkout DEV') {
            steps {
                echo "Checking out DEV branch..."
                checkout scm
            }
        }

        stage('Build') {
            steps {
                echo "Building application..."
            }
        }

        stage('Test') {
            steps {
                echo "Running tests..."
                sh 'echo "Tests successful"'
            }
        }

        stage('Production Approval') {
            steps {

                input(
                    message: 'DEV build is ready. Deploy this code to PRODUCTION?',
                    ok: 'DEPLOY TO PROD',
                    submitter: 'gaurav'
                )

            }
        }

        stage('Merge DEV → PROD') {
            steps {

                withCredentials([
                    usernamePassword(
                        credentialsId: 'github-credentials',
                        usernameVariable: 'GIT_USERNAME',
                        passwordVariable: 'GIT_TOKEN'
                    )
                ]) {

                    sh '''
                        set -e

                        echo "Configuring Git..."

                        git config user.name "Jenkins"
                        git config user.email "jenkins@yourcompany.com"

                        echo "Fetching latest branches..."
                        git fetch origin

                        echo "Checking out PROD..."
                        git checkout -B prod origin/prod

                        echo "Merging DEV into PROD..."
                        git merge origin/dev --ff-only

                        echo "Pushing PROD to GitHub..."

                        git push https://${GIT_USERNAME}:${GIT_TOKEN}@github.com/gaurav-patil-07/demo-repo.git prod:prod

                        echo "PROD push successful!"
                    '''
                }
            }
        }

        stage('Deploy Production') {
            steps {
                echo "Deploying PROD..."

                // Add your actual deployment commands here
            }
        }
    }

    post {

        success {
            echo "================================="
            echo "PRODUCTION DEPLOYMENT SUCCESSFUL"
            echo "================================="
        }

        aborted {
            echo "================================="
            echo "PRODUCTION DEPLOYMENT REJECTED"
            echo "================================="
        }

        failure {
            echo "================================="
            echo "PRODUCTION DEPLOYMENT FAILED"
            echo "================================="
        }
    }
}
