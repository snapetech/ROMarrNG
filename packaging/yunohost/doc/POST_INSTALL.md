Open the installed domain and set ROMarrNG's password on the first visit.
Configure indexers, download clients, and library connections in the Settings
pages.

The service listens only on localhost behind YunoHost's Nginx proxy. Its
YunoHost permission defaults to administrators. Give the romarrng service
account access to any existing library or download folders it should use.

ROMarrNG creates a default library directory under its persistent app data
directory. App backups intentionally omit library files and logs; back those
up separately. Settings, history, API credentials, and installed ROM Hub
plugins are included in the app data snapshot.
