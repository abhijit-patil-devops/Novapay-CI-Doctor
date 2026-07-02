pipeline {
    agent any

    stages {
        stage('Build') {
            steps {
                echo 'Building the application...'
                // Simulate a failure for testing
                sh 'exit 1'
            }
        }
    }

    post {
        failure {
            script {
                echo 'Build failed. Invoking Novapay CI Doctor...'

                // 1. Save the current build console log to a file in the workspace
                // Jenkins console logs are available at ${BUILD_URL}consoleText
                sh "curl -s ${BUILD_URL}consoleText > build.log"

                // 2. Run the Novapay CI Doctor Docker container
                // We mount the workspace so the container can read build.log
                // We pass the necessary environment variables for the AI and Email
                sh """
                docker run --rm \
                    -v ${WORKSPACE}:/app \
                    -e ANTHROPIC_API_KEY=your_api_key_here \
                    -e SMTP_HOST=smtp.gmail.com \
                    -e SMTP_PORT=587 \
                    -e SMTP_USERNAME=youremail@gmail.com \
                    -e SMTP_PASSWORD=your_app_password \
                    -e EMAIL_FROM=youremail@gmail.com \
                    -e EMAIL_TO=recipient@gmail.com \
                    novapay-ci-doctor \
                    --log-file /app/build.log \
                    --pipeline "${env.JOB_NAME}" \
                    --stage "Build" \
                    --build "${env.BUILD_NUMBER}"
                """
            }
        }
    }
}
