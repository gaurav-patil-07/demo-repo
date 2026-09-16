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

                sh '''
                    git config user.name "Jenkins"
                    git config user.email "jenkins@yourcompany.com"

                    git fetch origin

                    git checkout -B prod origin/prod

                    git merge origin/dev --ff-only

                    git push origin prod:prod
                '''
            }
        }

        stage('Deploy Production') {
            steps {
                echo "Deploying PROD..."
                
                // Add your actual deployment commands
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
