# SOVEREIGN AGENTS — SETUP GUIDE
# Phone-first. No PC required after this.
# Estimated time: 25 minutes

══════════════════════════════════════════════════════
STEP 1 — CREATE YOUR FREE API ACCOUNTS (browser, 10 min)
══════════════════════════════════════════════════════

1a. GEMINI API KEY (free, 1M tokens/day)
    - Open: https://aistudio.google.com/apikey
    - Sign in with Google
    - Click "Create API Key"
    - Copy and save the key somewhere safe

1b. MODAL ACCOUNT (free tier, serverless compute)
    - Open: https://modal.com
    - Sign up (GitHub login is fastest)
    - You will get your workspace name — note it down
      (looks like: your-name-personal)

══════════════════════════════════════════════════════
STEP 2 — SUPABASE: CREATE THE TABLE (browser, 3 min)
══════════════════════════════════════════════════════

    - Open: https://supabase.com/dashboard
    - Open your existing project (YOUR_PROJECT_ID)
    - Left sidebar: click "SQL Editor"
    - Click "New query"
    - Copy the ENTIRE contents of: supabase/schema.sql
    - Paste it into the editor
    - Click "Run"
    - You should see "Success" and no errors
    - Verify: click "Table Editor" in the sidebar — you should see "agent_sessions"

══════════════════════════════════════════════════════
STEP 3 — MODAL SECRETS (browser, 3 min)
══════════════════════════════════════════════════════

    - Open: https://modal.com/secrets
    - Click "Create new secret"
    - Name it EXACTLY: sovereign-agents-secrets
    - Add these three key-value pairs:

      Key: GEMINI_API_KEY
      Value: [your Gemini API key from Step 1a]

      Key: SUPABASE_URL
      Value: https://YOUR_PROJECT_ID.supabase.co

      Key: SUPABASE_SERVICE_KEY
      Value: YOUR_SUPABASE_SERVICE_KEY

    - Click "Save"

══════════════════════════════════════════════════════
STEP 4 — INSTALL MODAL IN A-SHELL (a-Shell app, 5 min)
══════════════════════════════════════════════════════

    Open a-Shell on your iPhone and run these commands one by one.
    Wait for each to finish before running the next.

    pip install modal

    modal token new
    (This opens a browser window — approve it to link your Modal account)

    pip install pyyaml

    Verify it worked:
    modal --version
    (Should print something like: 0.73.x)

══════════════════════════════════════════════════════
STEP 5 — TRANSFER PROJECT FILES TO a-Shell (5 min)
══════════════════════════════════════════════════════

    You need to get the modal_app folder onto your iPhone.
    Two options:

    OPTION A — iCloud Drive (easiest)
    - On your computer (or via the Files app on iPhone):
      Copy the entire modal_app folder to iCloud Drive
    - In a-Shell:
      cp -r ~/iCloud/modal_app ~/modal_app
      cd ~/modal_app

    OPTION B — Direct download from GitHub (if you push the code there)
    - Create a free GitHub repo and push the files
    - In a-Shell:
      git clone https://github.com/YOUR_USERNAME/sovereign-agents
      cd sovereign-agents/modal_app

    OPTION C — Paste files manually in a-Shell
    - In a-Shell: mkdir ~/modal_app && cd ~/modal_app
    - Use `cat > app.py` then paste content, then Ctrl+D
    - Repeat for each config file:
      mkdir configs && cat > configs/cct_math_validator.yaml (paste, Ctrl+D)
      [repeat for all 12 configs]

══════════════════════════════════════════════════════
STEP 6 — DEPLOY TO MODAL (a-Shell, 2 min)
══════════════════════════════════════════════════════

    In a-Shell, from inside the modal_app directory:

    cd ~/modal_app
    modal deploy app.py

    Wait for it to complete. It will take 30-45 seconds the first time
    (building the Docker image). You will see output like:

      Created objects.
      ├── Function api => https://YOUR-WORKSPACE--sovereign-agents-api.modal.run
      └── ...

    COPY THAT URL. It looks like:
    https://your-name-personal--sovereign-agents-api.modal.run

    That is your MODAL_URL. Save it.

══════════════════════════════════════════════════════
STEP 7 — CONFIGURE THE FRONTEND (1 min)
══════════════════════════════════════════════════════

    Open netlify_ui/index.html in a text editor (or Files app).
    Find this line near the top of the <script> section:

      const MODAL_URL = "REPLACE_WITH_YOUR_MODAL_URL";

    Replace it with your actual URL from Step 6:

      const MODAL_URL = "https://your-name-personal--sovereign-agents-api.modal.run";

    Save the file.

══════════════════════════════════════════════════════
STEP 8 — DEPLOY THE FRONTEND TO NETLIFY (2 min)
══════════════════════════════════════════════════════

    - Open: https://app.netlify.com
    - Sign up free (GitHub login fastest)
    - From the dashboard: "Add new site" > "Deploy manually"
    - Drag and drop the netlify_ui folder
      (or just the index.html file)
    - Netlify gives you a URL like: https://random-name-12345.netlify.app
    - Open that URL on your phone

    You should see: Sovereign Agents with green "online" status dot.

══════════════════════════════════════════════════════
STEP 9 — TEST IT (2 min)
══════════════════════════════════════════════════════

    In the UI:
    - Select "Cct Math Validator"
    - Paste this test input:
      "Model receptor binding as: dR/dt = kon * L * (Rtotal - R) - koff * R
       where L is free ligand concentration, R is bound receptor,
       Rtotal is total receptor density. Find the steady-state occupancy."
    - Hit Run
    - Wait ~30-60 seconds
    - You should see a validated mathematical output with Python code

    If it works: you are live.

══════════════════════════════════════════════════════
ONGOING USE — NO COMMANDS NEEDED AFTER THIS
══════════════════════════════════════════════════════

    Your Netlify URL is your permanent interface. Bookmark it.
    Modal runs automatically in the cloud when you hit Run.
    All results save to Supabase automatically.

    TO VIEW DATA DIRECTLY IN SUPABASE:
    - https://supabase.com/dashboard > your project > Table Editor > agent_sessions
    - You can filter, sort, and export from there
    - The "final_output" and "agent_turns" columns hold all session data

    TO ADD A NEW CONFIG LATER:
    - Create a new .yaml file following the same structure as any existing config
    - Run `modal deploy app.py` once from a-Shell to push the update
    - The new config appears in the UI automatically on next page load

    TO UPDATE AN EXISTING CONFIG:
    - Edit the .yaml file
    - Run `modal deploy app.py`
    - Done

══════════════════════════════════════════════════════
COST SUMMARY
══════════════════════════════════════════════════════

    Gemini API:    Free (1M tokens/day on Flash model)
    Modal:         Free tier covers ~$30/month compute
                   A typical 6-turn debate costs ~$0.002 on Modal compute
                   You can run ~15,000 sessions/month before hitting paid tier
    Supabase:      Already paying — no additional cost
    Netlify:       Free tier (100GB bandwidth/month)

    Effective cost: $0/month for normal research use.

══════════════════════════════════════════════════════
TROUBLESHOOTING
══════════════════════════════════════════════════════

    "Failed to load configs" in UI
    → MODAL_URL is wrong or Modal is not deployed. Re-check Step 6 URL.

    "offline" status in UI header
    → Modal container is cold-starting (first request after idle takes ~2s).
      Refresh the page and try again.

    modal deploy fails in a-Shell
    → Run: modal token new  (re-authenticate)
    → Make sure you are inside the modal_app directory (cd ~/modal_app)

    Supabase insert fails (500 error from Modal)
    → Check the secret values in Modal dashboard match exactly
    → The service key must start with sb_secret_

    Agents reach MAX_TURNS_REACHED instead of VERIFIED
    → Normal for complex inputs — the final output is still valid
    → Increase max_turns in the relevant config yaml and redeploy
