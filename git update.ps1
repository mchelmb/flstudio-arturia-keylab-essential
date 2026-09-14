# Initialize your local folder as a Git repository
git init

# Stage all your local files (Note: the dot works perfectly in PowerShell)
git add .

# Commit your files locally
git commit -m "Initial commit of my independent code"

# Ensure your default local branch is named 'main'
git branch -M main

# Link your local repository to your online GitHub fork
# *Make sure to replace YOUR_USERNAME and YOUR_FORKED_REPO with your actual details*
git remote add origin https://github.com/mchelmb/flstudio-arturia-keylab-essential
