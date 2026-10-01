# ROMarrNG on YunoHost

## Service access

The YunoHost permission defaults to admins. ROMarrNG's own password login
stays enabled as a second access layer. To let additional YunoHost users reach
the app, adjust its permission in the YunoHost admin interface; do not disable
ROMarrNG authentication unless another trusted access layer protects the
domain.

The service binds to 127.0.0.1 on the allocated port. YunoHost's Nginx proxy
is the only network entry point. Check service status and logs in the YunoHost
admin interface or with:

    sudo yunohost service status romarrng
    sudo yunohost service log romarrng
    sudo journalctl -u romarrng

## Library and download folders

The process runs as the YunoHost system account romarrng. Grant that account
read access to the ROM library and completed-download paths, and write access
to the folders where it must move or file downloads. ROMarrNG's default
library lives under /home/yunohost.app/romarrng/library; change the library
path in Settings → Media Management to use an existing or separately
mounted volume. The library and external download folders are not included in
YunoHost backups.

## Data, backup, and upgrades

Settings, history, the API key, password state, and ROM Hub plugins live in
/home/yunohost.app/romarrng/. A backup stops the service briefly to snapshot
that state consistently. Library files and logs are excluded.

The package pins a published ROMarrNG GitHub release archive and checks its
SHA-256 digest before installing it. YunoHost's GitHub tag updater proposes
package metadata updates for later ROMarrNG releases. Package updates install
the selected release into a Python virtual environment and leave persistent
app data in place.

## Package maintenance

The canonical package lives in the ROMarrNG source repository under
`packaging/yunohost`. The companion YunoHost-Apps repository mirrors that
directory at its root. After cloning the companion repository beside ROMarrNG,
install the source repository's post-commit hook with:

    ./scripts/install-yunohost-sync-hook.sh

Commits on ROMarrNG's main branch then sync the committed package files to the
companion repository's testing branch. Keep main as the reviewed package
version for catalog installs.
