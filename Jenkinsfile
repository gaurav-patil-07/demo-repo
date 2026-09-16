pipeline {

    agent any

    stages {

        stage('Checkout DEV') {
            steps {
                echo "Checking out dev branch"
                checkout scm
            }
        }

        stage('Build') {
            steps {
                echo "Building application"
                echo "Build successful"
            }
        }

        stage('Test') {
            steps {
                sh '''
                    echo "Running tests..."
                    echo "Tests successful"
                '''
            }
        }

        stage('Manager 1 Approval') {
            steps {
                emailext(
                    to: 'manager1@augtrans.com',
                    subject: "Approval needed: Build #${env.BUILD_NUMBER}",
                    body: "A new build is ready for production.\n\nPlease review and approve: ${env.BUILD_URL}input/"
                )

                input(
                    message: 'DEV build passed tests. Approve for production?',
                    ok: 'APPROVE',
                    submitter: 'manager1_username'
                )
            }
        }

        stage('Manager 2 Approval') {
            steps {
                emailext(
                    to: 'manager2@augtrans.com',
                    subject: "Approval needed: Build #${env.BUILD_NUMBER}",
                    body: "Manager 1 has approved this build.\n\nPlease review and give final approval: ${env.BUILD_URL}input/"
                )

                input(
                    message: 'Manager 1 approved. Give final approval for production?',
                    ok: 'APPROVE',
                    submitter: 'manager2_username'
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
                        git config user.name "Jenkins"
                        git config user.email "jenkins@augtrans.com"
                        git fetch origin
                        git checkout -B prod origin/prod
                        git merge origin/dev --ff-only
                        git push https://${GIT_USERNAME}:${GIT_TOKEN}@github.com/gaurav-patil-07/demo-repo.git prod:prod
                    '''
                }
            }
        }

        stage('Deploy Production') {
            steps {
                echo "Deploying to production"
                // Put your actual deployment commands here
                echo "Production deployment successful"
            }
        }
    }

    post {
        success {
            emailext(
                to: 'manager1@augtrans.com, manager2@augtrans.com',
                subject: "Deployed: Build #${env.BUILD_NUMBER}",
                body: "The build has been successfully deployed to production."
            )
        }

        aborted {
            emailext(
                to: 'manager1@augtrans.com, manager2@augtrans.com',
                subject: "Rejected: Build #${env.BUILD_NUMBER}",
                body: "Deployment was rejected or aborted at the approval stage."
            )
        }

        failure {
            echo "Pipeline failed"
        }
    }
}
