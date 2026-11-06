# Discord modlists

## Add a pack

1. Upload an Arma 3 Launcher HTML export and a PNG named `banner.png` to a new folder on `main`, for example `modpacks/cold-war/`. Use lowercase letters, numbers and hyphens for the folder name. Put exactly one HTML file in each folder. Its filename supplies the card title. A 720 × 200 banner matches WW2.
2. Open **Actions → Add modpack → Run workflow**. Enter the folder name, such as `cold-war`, and leave the mode set to **preview**. Open the run's **Summary** to see the heading, banner and details.
3. When it looks right, run **Add modpack** again from `main` with the same folder and mode **post**. The workflow posts the card using the shared webhook and saves its ID as `discord-message-id.txt` inside the pack folder. Leave that file in place.

## Update a pack

Replace its HTML or banner in the same folder and commit to `main`. The sync refreshes registered cards using their saved IDs. For a manual preview or refresh of one card, use **Actions → Sync Discord modlists** and enter the folder name. Use `ww2` for the original pack.

Edit `.github/discord-modlist-message.md` for shared wording. Keep the title on the first line, followed by the body. Use `$$` for a literal dollar sign. Configure publisher-verified, publicly available Steam Workshop compatibility links in `.github/discord-dlc-compatibility.json`, using the exact DLC display name as the key.

## Recover an interrupted post

A saved ID of `pending` stops retries from creating a duplicate. Check the original Actions run and the Discord channel. If the card exists, replace `pending` with that card's numeric message ID. If you confirm the card was never created, remove the marker and run **post** again. Keep the existing `DISCORD_WEBHOOK_URL` repository secret.
