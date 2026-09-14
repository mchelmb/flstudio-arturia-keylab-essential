# 1. Initialize Git in your local folder if you haven't already
git init

# 2. Stage all your local files (including your custom README.md)
git add .

# 3. Commit your files locally
git commit -m "Overwrite repo with local code"

# 4. Set your local branch name to 'main'
git branch -M main

# 5. Link your local project to your online GitHub fork
# (Skip this step if you already added the origin earlier)
git remote add origin https://github.com/mchelmb/flstudio-arturia-keylab-essential

# 6. FORCE PUSH to overwrite the online repository completely
git push -u origin main --force
