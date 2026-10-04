#!/bin/bash

#=================================================
# COMMON VARIABLES AND CUSTOM HELPERS
#=================================================

#=================================================
# PERSONAL HELPERS
#=================================================

romarrng_prepare_data() {
	local directory

	for directory in "$data_dir/library" "$data_dir/rom-hub"; do
		if [[ -L "$directory" ]]; then
			ynh_die --message="Refusing to use a symlink for ROMarrNG data directory: $directory"
		fi
		if [[ -e "$directory" && ! -d "$directory" ]]; then
			ynh_die --message="ROMarrNG data path is not a directory: $directory"
		fi
	done

	if [[ -L "$data_dir/romarr.json" ]]; then
		ynh_die --message="Refusing to read ROMarrNG state through a symlink."
	fi
	if [[ -e "$data_dir/romarr.json" && ! -f "$data_dir/romarr.json" ]]; then
		ynh_die --message="ROMarrNG state path exists but is not a regular file."
	fi

	install -d -o "$app" -g "$app" -m 0750 \
		"$data_dir/library" "$data_dir/rom-hub"
	chmod 0750 "$data_dir"
	chown "$app:$app" "$data_dir"
}

romarrng_install_python_dependencies() {
	local uv_dir="$install_dir/uv"
	local uv_bin="$uv_dir/uv"

	ynh_setup_source --dest_dir="$uv_dir" --source_id="uv" --full_replace
	chown -R root:root "$uv_dir"
	chmod 0755 "$uv_bin"

	ynh_exec_as_app "$uv_bin" venv \
		--python 3.13 \
		--no-managed-python \
		"$install_dir/venv"
	ynh_hide_warnings ynh_exec_as_app "$uv_bin" pip install \
		--python "$install_dir/venv/bin/python" \
		--no-cache \
		--requirement "$install_dir/requirements.txt" \
		"rom-hub @ https://github.com/BlizzHacker/rom-hub/archive/8e46348783546ee03b00e2c933155ba60d29619d.tar.gz"
}

romarrng_prepare_service() {
	local log_dir="/var/log/$app"
	local log_file="$log_dir/$app.log"

	if [[ -L "$log_dir" ]]; then
		ynh_die --message="Refusing to use a symlink as ROMarrNG's log directory."
	fi
	if [[ -e "$log_dir" && ! -d "$log_dir" ]]; then
		ynh_die --message="ROMarrNG log path exists but is not a directory."
	fi
	install -d -o "$app" -g "$app" -m 0750 "$log_dir"
	install -o "$app" -g "$app" -m 0640 /dev/null "$log_file"

	ynh_config_add_nginx
	ynh_config_add_systemd
	ynh_config_add_logrotate "$log_file"
}

romarrng_start_service() {
	local log_file="/var/log/$app/$app.log"

	ynh_systemctl --service="$app" --action="start" \
		--wait_until="ROMarr listening on" \
		--log_path="$log_file"
}

romarrng_register_service() {
	local log_file="/var/log/$app/$app.log"

	yunohost service add "$app" \
		--description="ROMarrNG game library and acquisition service" \
		--log="$log_file"
}
