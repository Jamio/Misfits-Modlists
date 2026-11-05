# Discord modlist sync

- Edit `discord-modlist-message.md` in this folder to change the shared wording. Keep any placeholders you want the workflow to fill in. Use `$$` for a literal dollar sign.
- To enable an optional compatibility link, confirm that the DLC publisher links to the Workshop item and that non-owners can access it. Add the exact DLC display name as the key and the canonical HTTPS Steam Workshop item URL as the value in `discord-dlc-compatibility.json`. Remove an entry to hide its link.
- Changes to the preset, template, compatibility list, or workflow on `main` trigger a sync. To preview manually, open **Actions → Sync WW2 modlist to Discord → Run workflow** and leave **Preview the message without contacting Discord** checked. Uncheck it on `main` to apply the edit manually.
- Keep `DISCORD_WEBHOOK_URL` and `discord-ww2-message-id.txt` in place. If Discord rejects the edit, check that the saved message still exists and belongs to that webhook. The workflow only edits the saved message.
