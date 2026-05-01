# Po prvním nasazení na Render

1. Render → tvoje Web Service → **Settings** → **Deploy Hook** → Create hook → zkopíruj URL.
2. GitHub → repo → **Settings** → **Secrets and variables** → **Actions** → New repository secret  
   Name: `RENDER_DEPLOY_HOOK_URL` · Value: vložený odkaz.
3. **Actions** → workflow **Redeploy Render** → **Run workflow** (volitelně při každém pushi můžeš hook přidat jako druhý job později).

Netlify po propojení s GitHubem nasazuje automaticky při pushi do větve, kterou sleduješ.
