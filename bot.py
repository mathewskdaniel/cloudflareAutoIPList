#!/usr/bin/env python3

import ipaddress
import json
import subprocess
import threading
import time
import os
import urllib.error
import urllib.request
from datetime import datetime


# ============================================================
# CONFIG
# ============================================================

CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "config.env"
)


def load_config(path):
    config = {}

    with open(path, "r") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)

            key = key.strip()
            value = value.strip().strip('"').strip("'")

            config[key] = value

    return config


CONFIG = load_config(CONFIG_FILE)

CF_API_TOKEN = CONFIG["CF_API_TOKEN"]
CF_ACCOUNT_ID = CONFIG["CF_ACCOUNT_ID"]
CF_LIST_ID = CONFIG["CF_LIST_ID"]

TG_BOT_TOKEN = CONFIG["TG_BOT_TOKEN"]
TG_CHAT_ID = CONFIG["TG_CHAT_ID"]

CHECK_INTERVAL = int(
    CONFIG.get("CHECK_INTERVAL", "3600")
)

ALLOWED_USERS = {
    x.strip()
    for x in CONFIG.get(
        "ALLOWED_USERS",
        ""
    ).split()
    if x.strip()
}

HOME_COMMENT = CONFIG.get(
    "HOME_COMMENT",
    "managed-home-ip"
)

CUSTOM_COMMENT = CONFIG.get(
    "CUSTOM_COMMENT",
    "managed-custom-ip"
)


# ============================================================
# RUNTIME STATE
# ============================================================

UPDATE_LOCK = threading.Lock()

PENDING_ADD = {}

STATE_LOCK = threading.Lock()


# ============================================================
# LOGGING
# ============================================================

def log(message):
    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print(
        f"[{timestamp}] {message}",
        flush=True
    )


# ============================================================
# GENERIC HTTP
# ============================================================

def http_request(
    url,
    method="GET",
    headers=None,
    data=None,
    timeout=15
):
    if headers is None:
        headers = {}

    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout
    ) as response:

        body = response.read().decode(
            "utf-8"
        )

        try:
            return (
                response.status,
                json.loads(body)
            )

        except json.JSONDecodeError:
            return (
                response.status,
                body
            )


# ============================================================
# TELEGRAM API
# ============================================================

def telegram_request(
    method,
    payload=None,
    timeout=15
):
    if payload is None:
        payload = {}

    url = (
        f"https://api.telegram.org/"
        f"bot{TG_BOT_TOKEN}/{method}"
    )

    command = [
        "curl",
        "-4",
        "-sS",
        "--connect-timeout",
        "5",
        "--max-time",
        str(timeout),
        "-X",
        "POST",
        url
    ]

    for key, value in payload.items():

        if isinstance(
            value,
            (dict, list)
        ):
            value = json.dumps(
                value,
                separators=(",", ":")
            )

        command.extend([
            "--data-urlencode",
            f"{key}={value}"
        ])

    try:

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout + 5
        )

        if result.returncode != 0:

            log(
                "Telegram curl error: "
                f"{result.stderr.strip()}"
            )

            return None

        if not result.stdout.strip():
            return None

        response = json.loads(
            result.stdout
        )

        return response

    except Exception as e:

        log(
            f"Telegram request error: {e}"
        )

        return None


def send_telegram(
    chat_id,
    text,
    reply_markup=None
):
    payload = {
        "chat_id": str(chat_id),
        "text": text
    }

    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    return telegram_request(
        "sendMessage",
        payload,
        timeout=10
    )


def edit_telegram_message(
    chat_id,
    message_id,
    text,
    reply_markup=None
):
    payload = {
        "chat_id": str(chat_id),
        "message_id": str(message_id),
        "text": text
    }

    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    result = telegram_request(
        "editMessageText",
        payload,
        timeout=10
    )

    if result and not result.get("ok"):
        log(
            "Telegram editMessageText failed: "
            f"{result}"
        )

    return result


def answer_callback(
    callback_id,
    text=None
):
    payload = {
        "callback_query_id": str(callback_id)
    }

    if text:
        payload["text"] = text

    result = telegram_request(
        "answerCallbackQuery",
        payload,
        timeout=10
    )

    if result and not result.get("ok"):
        log(
            "Telegram answerCallbackQuery failed: "
            f"{result}"
        )

    return result


# ============================================================
# TELEGRAM KEYBOARDS
# ============================================================

def main_menu_keyboard():
    return {
        "inline_keyboard": [
            [
                {
                    "text": "🔄 Update Home IP",
                    "callback_data": "home_update"
                }
            ],
            [
                {
                    "text": "➕ Add Custom IP",
                    "callback_data": "custom_add"
                },
                {
                    "text": "🗑 Delete Custom IP",
                    "callback_data": "custom_delete"
                }
            ],
            [
                {
                    "text": "📋 List",
                    "callback_data": "list"
                },
                {
                    "text": "📊 Status",
                    "callback_data": "status"
                }
            ]
        ]
    }


def list_keyboard():
    return {
        "inline_keyboard": [
            [
                {
                    "text": "🔄 Update Home IP",
                    "callback_data": "home_update"
                }
            ],
            [
                {
                    "text": "➕ Add Custom IP",
                    "callback_data": "custom_add"
                },
                {
                    "text": "🗑 Delete Custom IP",
                    "callback_data": "custom_delete"
                }
            ],
            [
                {
                    "text": "🔃 Refresh List",
                    "callback_data": "list"
                },
                {
                    "text": "📊 Status",
                    "callback_data": "status"
                }
            ],
            [
                {
                    "text": "🏠 Main Menu",
                    "callback_data": "menu"
                }
            ]
        ]
    }


def cancel_keyboard():
    return {
        "inline_keyboard": [
            [
                {
                    "text": "❌ Cancel",
                    "callback_data": "cancel"
                }
            ]
        ]
    }


def back_keyboard():
    return {
        "inline_keyboard": [
            [
                {
                    "text": "🏠 Main Menu",
                    "callback_data": "menu"
                },
                {
                    "text": "📋 List",
                    "callback_data": "list"
                }
            ]
        ]
    }


# ============================================================
# MAIN MENU
# ============================================================

def show_main_menu(
    chat_id,
    message_id=None
):
    text = (
        "🤖 Cloudflare List Bot\n\n"
        "Choose an action:"
    )

    keyboard = main_menu_keyboard()

    if message_id:

        edit_telegram_message(
            chat_id,
            message_id,
            text,
            keyboard
        )

    else:

        send_telegram(
            chat_id,
            text,
            keyboard
        )


# ============================================================
# CLOUDFLARE CONFIG
# ============================================================

CF_BASE_URL = (
    f"https://api.cloudflare.com/client/v4/"
    f"accounts/{CF_ACCOUNT_ID}/rules/lists/"
    f"{CF_LIST_ID}"
)

CF_ITEMS_URL = (
    f"{CF_BASE_URL}/items"
)


def cloudflare_headers():
    return {
        "Authorization":
            f"Bearer {CF_API_TOKEN}",
        "Content-Type":
            "application/json"
    }


# ============================================================
# CLOUDFLARE LIST
# ============================================================

def get_all_cloudflare_items():

    try:

        status, result = http_request(
            CF_ITEMS_URL,
            method="GET",
            headers=cloudflare_headers(),
            timeout=15
        )

        if status != 200:

            log(
                f"Cloudflare list GET "
                f"HTTP {status}"
            )

            log(
                str(result)
            )

            return None

        if not result.get("success"):

            log(
                "Cloudflare list GET failed: "
                f"{result}"
            )

            return None

        return result.get(
            "result",
            []
        )

    except urllib.error.HTTPError as e:

        try:
            body = e.read().decode(
                "utf-8"
            )
        except Exception:
            body = ""

        log(
            f"Cloudflare GET HTTP "
            f"{e.code}: {body}"
        )

        return None

    except Exception as e:

        log(
            f"Cloudflare GET error: {e}"
        )

        return None


def get_home_entry(
    items=None
):

    if items is None:
        items = get_all_cloudflare_items()

    if items is None:
        return None

    for item in items:

        if item.get(
            "comment"
        ) == HOME_COMMENT:

            return item

    return None


# ============================================================
# IP FUNCTIONS
# ============================================================

def normalize_ip(value):

    value = value.strip()

    try:

        address = ipaddress.ip_address(
            value
        )

        if address.version == 4:
            return f"{address}/32"

        return f"{address}/128"

    except ValueError:
        pass

    try:

        network = ipaddress.ip_network(
            value,
            strict=False
        )

        return str(network)

    except ValueError:

        return None


def same_network(
    value1,
    value2
):

    try:

        net1 = ipaddress.ip_network(
            value1,
            strict=False
        )

        net2 = ipaddress.ip_network(
            value2,
            strict=False
        )

        return (
            net1.version == net2.version
            and net1 == net2
        )

    except ValueError:

        return False


def find_item_by_ip(
    ip,
    items=None
):

    if items is None:
        items = get_all_cloudflare_items()

    if items is None:
        return None

    for item in items:

        existing_ip = item.get(
            "ip"
        )

        if existing_ip and same_network(
            ip,
            existing_ip
        ):

            return item

    return None


def get_custom_items(
    items=None
):

    if items is None:
        items = get_all_cloudflare_items()

    if items is None:
        return []

    return [
        item
        for item in items
        if item.get(
            "comment"
        ) == CUSTOM_COMMENT
    ]


# ============================================================
# CLOUDFLARE ASYNC OPERATIONS
# ============================================================

def wait_for_operation(
    operation_id
):

    url = (
        f"https://api.cloudflare.com/client/v4/"
        f"accounts/{CF_ACCOUNT_ID}/rules/lists/"
        f"bulk_operations/{operation_id}"
    )

    log(
        f"Waiting for Cloudflare operation "
        f"{operation_id}"
    )

    for attempt in range(30):

        try:

            status, result = http_request(
                url,
                method="GET",
                headers=cloudflare_headers(),
                timeout=15
            )

            if status != 200:

                log(
                    f"Cloudflare operation "
                    f"HTTP {status}"
                )

            elif result.get(
                "success"
            ):

                operation = result.get(
                    "result",
                    {}
                )

                operation_status = (
                    operation.get(
                        "status"
                    )
                )

                log(
                    f"Operation "
                    f"{operation_id}: "
                    f"{operation_status}"
                )

                if operation_status == "completed":
                    return True

                if operation_status in (
                    "failed",
                    "error"
                ):

                    log(
                        f"Operation failed: "
                        f"{result}"
                    )

                    return False

            else:

                log(
                    "Operation status failed: "
                    f"{result}"
                )

        except urllib.error.HTTPError as e:

            try:
                body = e.read().decode(
                    "utf-8"
                )
            except Exception:
                body = ""

            log(
                f"Operation HTTP "
                f"{e.code}: {body}"
            )

        except Exception as e:

            log(
                f"Error checking operation "
                f"{operation_id}: {e}"
            )

        time.sleep(2)

    log(
        f"Cloudflare operation "
        f"{operation_id} timed out"
    )

    return False


# ============================================================
# CLOUDFLARE ADD
# ============================================================

def add_cloudflare_item(
    ip,
    comment
):

    payload = [
        {
            "ip": ip,
            "comment": comment
        }
    ]

    log(
        f"Cloudflare ADD request: "
        f"ip={ip}, comment={comment}"
    )

    try:

        status, result = http_request(
            CF_ITEMS_URL,
            method="POST",
            headers=cloudflare_headers(),
            data=json.dumps(
                payload
            ).encode(),
            timeout=15
        )

        if status not in (
            200,
            201
        ):

            log(
                f"Cloudflare ADD "
                f"HTTP {status}"
            )

            log(
                f"Cloudflare response: "
                f"{result}"
            )

            return False

        if not result.get(
            "success"
        ):

            log(
                "Cloudflare ADD failed: "
                f"{result}"
            )

            return False

        result_data = result.get(
            "result",
            {}
        )

        if isinstance(
            result_data,
            dict
        ):

            operation_id = (
                result_data.get(
                    "operation_id"
                )
            )

        else:

            operation_id = result_data

        if not operation_id:

            log(
                "Cloudflare ADD returned "
                "no operation ID."
            )

            log(
                f"Full response: {result}"
            )

            return False

        log(
            f"Cloudflare ADD started: "
            f"{ip}, "
            f"operation={operation_id}"
        )

        return wait_for_operation(
            operation_id
        )

    except urllib.error.HTTPError as e:

        try:
            body = e.read().decode(
                "utf-8"
            )
        except Exception:
            body = ""

        log(
            f"Cloudflare ADD HTTP "
            f"{e.code}: {body}"
        )

        return False

    except Exception as e:

        log(
            f"Cloudflare ADD error: {e}"
        )

        return False


# ============================================================
# CLOUDFLARE DELETE
# ============================================================

def delete_cloudflare_item(
    item_id
):

    payload = {
        "items": [
            {
                "id": item_id
            }
        ]
    }

    log(
        f"Cloudflare DELETE request: "
        f"id={item_id}"
    )

    try:

        status, result = http_request(
            CF_ITEMS_URL,
            method="DELETE",
            headers=cloudflare_headers(),
            data=json.dumps(
                payload
            ).encode(),
            timeout=15
        )

        if status not in (
            200,
            201
        ):

            log(
                f"Cloudflare DELETE "
                f"HTTP {status}"
            )

            log(
                f"Cloudflare response: "
                f"{result}"
            )

            return False

        if not result.get(
            "success"
        ):

            log(
                "Cloudflare DELETE failed: "
                f"{result}"
            )

            return False

        result_data = result.get(
            "result",
            {}
        )

        if isinstance(
            result_data,
            dict
        ):

            operation_id = (
                result_data.get(
                    "operation_id"
                )
            )

        else:

            operation_id = result_data

        if not operation_id:

            log(
                "Cloudflare DELETE returned "
                "no operation ID."
            )

            log(
                f"Full response: {result}"
            )

            return False

        log(
            f"Cloudflare DELETE started: "
            f"id={item_id}, "
            f"operation={operation_id}"
        )

        return wait_for_operation(
            operation_id
        )

    except urllib.error.HTTPError as e:

        try:
            body = e.read().decode(
                "utf-8"
            )
        except Exception:
            body = ""

        log(
            f"Cloudflare DELETE HTTP "
            f"{e.code}: {body}"
        )

        return False

    except Exception as e:

        log(
            f"Cloudflare DELETE error: {e}"
        )

        return False


# ============================================================
# LOCAL IPV6
# ============================================================

def get_current_ipv6():

    try:

        result = subprocess.run(
            [
                "ip",
                "-6",
                "addr",
                "show",
                "scope",
                "global"
            ],
            capture_output=True,
            text=True,
            timeout=10
        )

        for line in result.stdout.splitlines():

            line = line.strip()

            if not line.startswith(
                "inet6 "
            ):
                continue

            address = (
                line.split()[1]
                .split("/")[0]
            )

            try:

                ip = ipaddress.IPv6Address(
                    address
                )

                if ip.is_private:
                    continue

                if ip.is_link_local:
                    continue

                return str(ip)

            except ValueError:
                continue

    except Exception as e:

        log(
            f"IPv6 detection error: {e}"
        )

    return None


def calculate_prefix(
    ipv6
):

    try:

        address = ipaddress.IPv6Address(
            ipv6
        )

        network = ipaddress.IPv6Network(
            f"{address}/64",
            strict=False
        )

        return str(network)

    except Exception as e:

        log(
            f"IPv6 prefix calculation error: "
            f"{e}"
        )

        return None


# ============================================================
# HOME IPV6 UPDATE
# ============================================================

def perform_home_update(
    source="Automatic",
    chat_id=None
):

    notify_chat = (
        chat_id
        if chat_id
        else TG_CHAT_ID
    )

    log(
        f"{source} home IPv6 check started"
    )

    current_ipv6 = get_current_ipv6()

    if not current_ipv6:

        message = (
            "❌ Could not detect a public "
            "global IPv6 address on the Pi."
        )

        log(message)

        send_telegram(
            notify_chat,
            message,
            list_keyboard()
        )

        return False

    current_prefix = calculate_prefix(
        current_ipv6
    )

    if not current_prefix:

        message = (
            "❌ Could not calculate "
            "the current IPv6 /64."
        )

        log(message)

        send_telegram(
            notify_chat,
            message,
            list_keyboard()
        )

        return False

    log(
        f"Current IPv6: "
        f"{current_ipv6}"
    )

    log(
        f"Current /64: "
        f"{current_prefix}"
    )

    items = get_all_cloudflare_items()

    if items is None:

        message = (
            "❌ Could not retrieve "
            "the Cloudflare list."
        )

        send_telegram(
            notify_chat,
            message,
            list_keyboard()
        )

        return False

    home_entry = get_home_entry(
        items
    )

    if home_entry:

        old_prefix = home_entry.get(
            "ip"
        )

        old_id = home_entry.get(
            "id"
        )

        log(
            f"Managed HOME entry: "
            f"{old_prefix} "
            f"(id={old_id})"
        )

        if same_network(
            current_prefix,
            old_prefix
        ):

            log(
                "Home IPv6 /64 unchanged."
            )

            send_telegram(
                notify_chat,
                "🔍 Home IPv6 check completed.\n\n"
                "Status: ✅ No change\n\n"
                f"Current /64: {current_prefix}",
                list_keyboard()
            )

            return True

    else:

        old_prefix = None
        old_id = None

        log(
            "No existing managed HOME "
            "entry was found."
        )

    # --------------------------------------------------------
    # ADD NEW HOME
    # --------------------------------------------------------

    log(
        f"Adding new HOME entry: "
        f"{current_prefix}"
    )

    if not add_cloudflare_item(
        current_prefix,
        HOME_COMMENT
    ):

        message = (
            "❌ Failed to add the new "
            "home IPv6 /64 to Cloudflare.\n\n"
            f"New /64: {current_prefix}"
        )

        log(message)

        send_telegram(
            notify_chat,
            message,
            list_keyboard()
        )

        return False

    # --------------------------------------------------------
    # DELETE OLD HOME
    # --------------------------------------------------------

    if old_id:

        log(
            f"Deleting old HOME entry: "
            f"{old_prefix}"
        )

        if not delete_cloudflare_item(
            old_id
        ):

            message = (
                "⚠️ New home IPv6 was added, "
                "but the old HOME entry could "
                "not be deleted.\n\n"
                f"New /64: {current_prefix}\n"
                f"Old /64: {old_prefix}"
            )

            log(message)

            send_telegram(
                notify_chat,
                message,
                list_keyboard()
            )

            return False

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    message = (
        "🔄 Home IPv6 updated.\n\n"
        f"Old /64: "
        f"{old_prefix or 'None'}\n"
        f"New /64: "
        f"{current_prefix}"
    )

    log(message)

    send_telegram(
        notify_chat,
        message,
        list_keyboard()
    )

    return True


# ============================================================
# BUILD LIST MESSAGE
# ============================================================

def build_list_message(
    items
):

    home_items = []
    custom_items = []
    other_items = []

    for item in items:

        comment = item.get(
            "comment",
            ""
        )

        if comment == HOME_COMMENT:

            home_items.append(item)

        elif comment == CUSTOM_COMMENT:

            custom_items.append(item)

        else:

            other_items.append(item)

    lines = []

    lines.append(
        "📋 Cloudflare IP List"
    )

    lines.append("")

    # HOME

    lines.append(
        f"🏠 HOME: "
        f"{len(home_items)}"
    )

    for item in home_items:

        lines.append(
            f"• {item.get('ip')}"
        )

    lines.append("")

    # CUSTOM

    lines.append(
        f"🛠 CUSTOM: "
        f"{len(custom_items)}"
    )

    for item in custom_items:

        lines.append(
            f"• {item.get('ip')}"
        )

    lines.append("")

    # OTHER

    lines.append(
        f"📦 OTHER: "
        f"{len(other_items)}"
    )

    for item in other_items:

        lines.append(
            f"• {item.get('ip')}"
            f" | "
            f"{item.get('comment') or 'No comment'}"
        )

    lines.append("")

    lines.append(
        f"Total entries: "
        f"{len(items)}"
    )

    return "\n".join(lines)


# ============================================================
# LIST
# ============================================================

def handle_list(
    chat_id,
    message_id=None
):

    log(
        f"/list requested by "
        f"{chat_id}"
    )

    items = get_all_cloudflare_items()

    if items is None:

        text = (
            "❌ Could not retrieve "
            "the Cloudflare list."
        )

        if message_id:

            edit_telegram_message(
                chat_id,
                message_id,
                text,
                list_keyboard()
            )

        else:

            send_telegram(
                chat_id,
                text,
                list_keyboard()
            )

        return

    text = build_list_message(
        items
    )

    keyboard = list_keyboard()

    if message_id:

        edit_telegram_message(
            chat_id,
            message_id,
            text,
            keyboard
        )

    else:

        send_telegram(
            chat_id,
            text,
            keyboard
        )


# ============================================================
# STATUS
# ============================================================

def handle_status(
    chat_id,
    message_id=None
):

    log(
        f"/status requested by "
        f"{chat_id}"
    )

    current_ipv6 = get_current_ipv6()

    if not current_ipv6:

        text = (
            "❌ Could not detect "
            "a public IPv6 address."
        )

        if message_id:

            edit_telegram_message(
                chat_id,
                message_id,
                text,
                back_keyboard()
            )

        else:

            send_telegram(
                chat_id,
                text,
                back_keyboard()
            )

        return

    current_prefix = calculate_prefix(
        current_ipv6
    )

    items = get_all_cloudflare_items()

    if items is None:

        text = (
            "❌ Could not retrieve "
            "the Cloudflare list."
        )

        if message_id:

            edit_telegram_message(
                chat_id,
                message_id,
                text,
                back_keyboard()
            )

        else:

            send_telegram(
                chat_id,
                text,
                back_keyboard()
            )

        return

    home_entry = get_home_entry(
        items
    )

    lines = [
        "📊 Bot Status",
        "",
        f"Local IPv6: {current_ipv6}",
        f"Local /64: {current_prefix}",
        ""
    ]

    if home_entry:

        home_ip = home_entry.get(
            "ip"
        )

        home_id = home_entry.get(
            "id"
        )

        lines.extend([
            f"Cloudflare HOME: {home_ip}",
            f"HOME ID: {home_id}",
            ""
        ])

        if same_network(
            current_prefix,
            home_ip
        ):

            lines.append(
                "Status: ✅ In sync"
            )

        else:

            lines.append(
                "Status: ⚠️ Update required"
            )

    else:

        lines.extend([
            "Cloudflare HOME: Not found",
            "Status: ⚠️ Update required"
        ])

    lines.extend([
        "",
        f"Check interval: "
        f"{CHECK_INTERVAL}s"
    ])

    text = "\n".join(lines)

    if message_id:

        edit_telegram_message(
            chat_id,
            message_id,
            text,
            back_keyboard()
        )

    else:

        send_telegram(
            chat_id,
            text,
            back_keyboard()
        )


# ============================================================
# ADD FLOW
# ============================================================

def start_add_flow(
    chat_id,
    message_id=None
):

    with STATE_LOCK:

        PENDING_ADD[
            str(chat_id)
        ] = True

    text = (
        "➕ Add Custom IP\n\n"
        "Send the IP address or network "
        "you want to add.\n\n"
        "Examples:\n"
        "• 1.2.3.4\n"
        "• 2001:db8::1\n"
        "• 1.2.3.0/24\n"
        "• 2001:db8::/64\n\n"
        "The entry will use the configured "
        "CUSTOM comment."
    )

    if message_id:

        edit_telegram_message(
            chat_id,
            message_id,
            text,
            cancel_keyboard()
        )

    else:

        send_telegram(
            chat_id,
            text,
            cancel_keyboard()
        )


def cancel_add_flow(
    chat_id
):

    with STATE_LOCK:

        PENDING_ADD.pop(
            str(chat_id),
            None
        )


# ============================================================
# ADD CUSTOM IP
# ============================================================

def handle_add(
    value,
    chat_id
):

    cancel_add_flow(
        chat_id
    )

    ip = normalize_ip(
        value
    )

    if not ip:

        send_telegram(
            chat_id,
            "❌ Invalid IP address or network.",
            list_keyboard()
        )

        return

    log(
        f"/add requested by "
        f"{chat_id}: {ip}"
    )

    # --------------------------------------------------------
    # Protect current HOME /64
    # --------------------------------------------------------

    current_ipv6 = get_current_ipv6()

    if current_ipv6:

        current_home_prefix = (
            calculate_prefix(
                current_ipv6
            )
        )

        if (
            current_home_prefix
            and same_network(
                ip,
                current_home_prefix
            )
        ):

            send_telegram(
                chat_id,
                "🛡️ Refused.\n\n"
                f"{ip} matches the current "
                "home IPv6 /64.\n"
                "The automatic HOME entry "
                "is protected.",
                list_keyboard()
            )

            return

    # --------------------------------------------------------
    # Get Cloudflare list
    # --------------------------------------------------------

    items = get_all_cloudflare_items()

    if items is None:

        send_telegram(
            chat_id,
            "❌ Could not retrieve "
            "the Cloudflare list.",
            list_keyboard()
        )

        return

    # --------------------------------------------------------
    # Existing entry
    # --------------------------------------------------------

    existing = find_item_by_ip(
        ip,
        items
    )

    if existing:

        comment = existing.get(
            "comment",
            ""
        )

        existing_id = existing.get(
            "id"
        )

        if comment == HOME_COMMENT:

            send_telegram(
                chat_id,
                "🛡️ Refused.\n\n"
                f"{ip} belongs to the "
                "protected HOME entry.",
                list_keyboard()
            )

            return

        send_telegram(
            chat_id,
            "⚠️ Entry already exists.\n\n"
            f"IP: {existing.get('ip')}\n"
            f"Comment: "
            f"{comment or 'None'}\n"
            f"ID: {existing_id}",
            list_keyboard()
        )

        return

    # --------------------------------------------------------
    # Add
    # --------------------------------------------------------

    log(
        f"Adding CUSTOM entry: {ip}"
    )

    if add_cloudflare_item(
        ip,
        CUSTOM_COMMENT
    ):

        send_telegram(
            chat_id,
            "✅ Custom IP added.\n\n"
            f"IP: {ip}\n"
            f"Comment: {CUSTOM_COMMENT}",
            list_keyboard()
        )

    else:

        send_telegram(
            chat_id,
            "❌ Failed to add "
            "the custom IP.",
            list_keyboard()
        )


# ============================================================
# DELETE MENU
# ============================================================

def show_delete_menu(
    chat_id,
    message_id=None
):

    items = get_all_cloudflare_items()

    if items is None:

        text = (
            "❌ Could not retrieve "
            "the Cloudflare list."
        )

        if message_id:

            edit_telegram_message(
                chat_id,
                message_id,
                text,
                back_keyboard()
            )

        else:

            send_telegram(
                chat_id,
                text,
                back_keyboard()
            )

        return

    custom_items = get_custom_items(
        items
    )

    if not custom_items:

        text = (
            "🗑 Delete Custom IP\n\n"
            "There are currently no "
            "custom IPs added by this bot."
        )

        if message_id:

            edit_telegram_message(
                chat_id,
                message_id,
                text,
                back_keyboard()
            )

        else:

            send_telegram(
                chat_id,
                text,
                back_keyboard()
            )

        return

    keyboard_rows = []

    for item in custom_items:

        item_id = item.get(
            "id"
        )

        ip = item.get(
            "ip",
            "Unknown"
        )

        keyboard_rows.append([
            {
                "text": f"🗑 {ip}",
                "callback_data":
                    f"delete_select:{item_id}"
            }
        ])

    keyboard_rows.append([
        {
            "text": "❌ Cancel",
            "callback_data": "cancel"
        }
    ])

    keyboard = {
        "inline_keyboard": keyboard_rows
    }

    text = (
        "🗑 Delete Custom IP\n\n"
        "Select the custom entry "
        "to delete:"
    )

    if message_id:

        edit_telegram_message(
            chat_id,
            message_id,
            text,
            keyboard
        )

    else:

        send_telegram(
            chat_id,
            text,
            keyboard
        )


# ============================================================
# DELETE CONFIRMATION
# ============================================================

def show_delete_confirmation(
    chat_id,
    message_id,
    item_id
):

    items = get_all_cloudflare_items()

    if items is None:

        edit_telegram_message(
            chat_id,
            message_id,
            "❌ Could not retrieve "
            "the Cloudflare list.",
            back_keyboard()
        )

        return

    selected = None

    for item in items:

        if str(
            item.get("id")
        ) == str(item_id):

            selected = item
            break

    if not selected:

        edit_telegram_message(
            chat_id,
            message_id,
            "❌ That entry no longer exists.",
            list_keyboard()
        )

        return

    comment = selected.get(
        "comment",
        ""
    )

    if comment == HOME_COMMENT:

        edit_telegram_message(
            chat_id,
            message_id,
            "🛡️ This is the protected "
            "HOME entry.\n\n"
            "Manual deletion is not allowed.",
            list_keyboard()
        )

        return

    if comment != CUSTOM_COMMENT:

        edit_telegram_message(
            chat_id,
            message_id,
            "🛡️ This entry was not "
            "created by this bot.\n\n"
            "Deletion refused.",
            list_keyboard()
        )

        return

    ip = selected.get(
        "ip",
        "Unknown"
    )

    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Delete",
                    "callback_data":
                        f"delete_confirm:{item_id}"
                },
                {
                    "text": "❌ Cancel",
                    "callback_data":
                        "custom_delete"
                }
            ]
        ]
    }

    edit_telegram_message(
        chat_id,
        message_id,
        "⚠️ Delete Custom IP?\n\n"
        f"IP: {ip}\n\n"
        "This will remove the entry "
        "from the Cloudflare list.",
        keyboard
    )


# ============================================================
# ACTUAL CUSTOM DELETE
# ============================================================

def perform_custom_delete(
    chat_id,
    message_id,
    item_id
):

    items = get_all_cloudflare_items()

    if items is None:

        edit_telegram_message(
            chat_id,
            message_id,
            "❌ Could not retrieve "
            "the Cloudflare list.",
            list_keyboard()
        )

        return

    selected = None

    for item in items:

        if str(
            item.get("id")
        ) == str(item_id):

            selected = item
            break

    if not selected:

        edit_telegram_message(
            chat_id,
            message_id,
            "❌ That entry no longer exists.",
            list_keyboard()
        )

        return

    ip = selected.get(
        "ip",
        "Unknown"
    )

    comment = selected.get(
        "comment",
        ""
    )

    # Final safety check

    if comment == HOME_COMMENT:

        edit_telegram_message(
            chat_id,
            message_id,
            "🛡️ HOME entry is protected.\n\n"
            "Deletion refused.",
            list_keyboard()
        )

        return

    if comment != CUSTOM_COMMENT:

        edit_telegram_message(
            chat_id,
            message_id,
            "🛡️ This is not a custom "
            "entry created by this bot.\n\n"
            "Deletion refused.",
            list_keyboard()
        )

        return

    edit_telegram_message(
        chat_id,
        message_id,
        "⏳ Deleting custom IP...\n\n"
        f"{ip}"
    )

    log(
        f"Deleting CUSTOM entry: "
        f"{ip}, id={item_id}"
    )

    success = delete_cloudflare_item(
        item_id
    )

    if success:

        edit_telegram_message(
            chat_id,
            message_id,
            "🗑 Custom IP deleted.\n\n"
            f"IP: {ip}",
            list_keyboard()
        )

    else:

        edit_telegram_message(
            chat_id,
            message_id,
            "❌ Failed to delete "
            "the custom IP.\n\n"
            f"IP: {ip}",
            list_keyboard()
        )


# ============================================================
# HOME UPDATE BUTTON
# ============================================================

def start_home_update(
    chat_id,
    message_id
):

    if not UPDATE_LOCK.acquire(
        blocking=False
    ):

        edit_telegram_message(
            chat_id,
            message_id,
            "⏳ A home IPv6 update "
            "is already running.",
            list_keyboard()
        )

        return

    edit_telegram_message(
        chat_id,
        message_id,
        "⏳ Updating Home IPv6...\n\n"
        "Please wait."
    )

    def worker():

        try:

            perform_home_update(
                source="Manual",
                chat_id=chat_id
            )

        finally:

            UPDATE_LOCK.release()

    threading.Thread(
        target=worker,
        daemon=True
    ).start()


# ============================================================
# CALLBACK HANDLER
# ============================================================

def handle_callback(
    callback
):

    try:

        callback_id = callback.get(
            "id"
        )

        data = callback.get(
            "data",
            ""
        )

        message = callback.get(
            "message",
            {}
        )

        chat = message.get(
            "chat",
            {}
        )

        chat_id = str(
            chat.get(
                "id",
                ""
            )
        )

        message_id = message.get(
            "message_id"
        )

        log(
            f"Callback received: "
            f"chat={chat_id}, "
            f"data={data}"
        )

        if not chat_id or not message_id:

            if callback_id:
                answer_callback(
                    callback_id
                )

            return

        # ----------------------------------------------------
        # AUTH
        # ----------------------------------------------------

        user_id = str(
            callback.get("from", {}).get("id", "")
        )

        if user_id not in ALLOWED_USERS:

            log(
                f"Unauthorized callback "
                f"user: {user_id}"
            )

            if callback_id:
                answer_callback(
                    callback_id
                )

            return

        # ----------------------------------------------------
        # ACKNOWLEDGE CALLBACK IMMEDIATELY
        # ----------------------------------------------------

        if callback_id:

            answer_callback(
                callback_id
            )

        # ----------------------------------------------------
        # MENU
        # ----------------------------------------------------

        if data == "menu":

            cancel_add_flow(
                chat_id
            )

            show_main_menu(
                chat_id,
                message_id
            )

            return

        # ----------------------------------------------------
        # LIST
        # ----------------------------------------------------

        if data == "list":

            cancel_add_flow(
                chat_id
            )

            handle_list(
                chat_id,
                message_id
            )

            return

        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------

        if data == "status":

            cancel_add_flow(
                chat_id
            )

            edit_telegram_message(
                chat_id,
                message_id,
                "⏳ Getting status..."
            )

            threading.Thread(
                target=handle_status,
                args=(
                    chat_id,
                    message_id
                ),
                daemon=True
            ).start()

            return

        # ----------------------------------------------------
        # HOME UPDATE
        # ----------------------------------------------------

        if data == "home_update":

            cancel_add_flow(
                chat_id
            )

            start_home_update(
                chat_id,
                message_id
            )

            return

        # ----------------------------------------------------
        # ADD CUSTOM
        # ----------------------------------------------------

        if data == "custom_add":

            start_add_flow(
                chat_id,
                message_id
            )

            return

        # ----------------------------------------------------
        # DELETE MENU
        # ----------------------------------------------------

        if data == "custom_delete":

            cancel_add_flow(
                chat_id
            )

            show_delete_menu(
                chat_id,
                message_id
            )

            return

        # ----------------------------------------------------
        # DELETE SELECT
        # ----------------------------------------------------

        if data.startswith(
            "delete_select:"
        ):

            item_id = data.split(
                ":",
                1
            )[1]

            show_delete_confirmation(
                chat_id,
                message_id,
                item_id
            )

            return

        # ----------------------------------------------------
        # DELETE CONFIRM
        # ----------------------------------------------------

        if data.startswith(
            "delete_confirm:"
        ):

            item_id = data.split(
                ":",
                1
            )[1]

            perform_custom_delete(
                chat_id,
                message_id,
                item_id
            )

            return

        # ----------------------------------------------------
        # CANCEL
        # ----------------------------------------------------

        if data == "cancel":

            cancel_add_flow(
                chat_id
            )

            show_main_menu(
                chat_id,
                message_id
            )

            return

        log(
            f"Unknown callback data: "
            f"{data}"
        )

    except Exception as e:

        log(
            f"Callback handler error: "
            f"{e}"
        )


# ============================================================
# LEGACY DELETE COMMAND
# ============================================================

def handle_delete_command(
    value,
    chat_id
):

    ip = normalize_ip(
        value
    )

    if not ip:

        send_telegram(
            chat_id,
            "❌ Invalid IP address or network.",
            list_keyboard()
        )

        return

    log(
        f"/delete requested by "
        f"{chat_id}: {ip}"
    )

    items = get_all_cloudflare_items()

    if items is None:

        send_telegram(
            chat_id,
            "❌ Could not retrieve "
            "the Cloudflare list.",
            list_keyboard()
        )

        return

    existing = find_item_by_ip(
        ip,
        items
    )

    if not existing:

        send_telegram(
            chat_id,
            f"ℹ️ {ip} was not found "
            "in the Cloudflare list.",
            list_keyboard()
        )

        return

    comment = existing.get(
        "comment",
        ""
    )

    item_id = existing.get(
        "id"
    )

    if comment == HOME_COMMENT:

        send_telegram(
            chat_id,
            "🛡️ Refused.\n\n"
            f"{ip} is the protected "
            "HOME entry.",
            list_keyboard()
        )

        return

    if comment != CUSTOM_COMMENT:

        send_telegram(
            chat_id,
            "🛡️ Refused.\n\n"
            f"{ip} exists in the "
            "Cloudflare list, but it is "
            "not a custom entry created "
            "by this bot.",
            list_keyboard()
        )

        return

    if delete_cloudflare_item(
        item_id
    ):

        send_telegram(
            chat_id,
            "🗑 Custom IP deleted.\n\n"
            f"IP: {ip}",
            list_keyboard()
        )

    else:

        send_telegram(
            chat_id,
            "❌ Failed to delete "
            "the custom IP.",
            list_keyboard()
        )


# ============================================================
# TELEGRAM MESSAGE HANDLER
# ============================================================

def handle_message(
    message
):

    try:

        chat = message.get(
            "chat",
            {}
        )

        chat_id = str(
            chat.get(
                "id",
                ""
            )
        )

        text = message.get(
            "text",
            ""
        )

        if not chat_id or not text:
            return

        # ----------------------------------------------------
        # AUTHORIZATION
        # ----------------------------------------------------

        if chat_id not in ALLOWED_USERS:

            log(
                f"Unauthorized Telegram "
                f"user: {chat_id}"
            )

            return

        text = text.strip()

        # ----------------------------------------------------
        # PENDING ADD INPUT
        # ----------------------------------------------------

        with STATE_LOCK:

            pending_add = PENDING_ADD.get(
                chat_id,
                False
            )

        if (
            pending_add
            and not text.startswith("/")
        ):

            threading.Thread(
                target=handle_add,
                args=(
                    text,
                    chat_id
                ),
                daemon=True
            ).start()

            return

        # ----------------------------------------------------
        # NORMAL TEXT
        # ----------------------------------------------------

        if not text.startswith("/"):
            return

        parts = text.split(
            maxsplit=1
        )

        command = (
            parts[0]
            .split("@")[0]
            .lower()
        )

        argument = (
            parts[1].strip()
            if len(parts) > 1
            else ""
        )

        # ----------------------------------------------------
        # /START
        # ----------------------------------------------------

        if command == "/start":

            cancel_add_flow(
                chat_id
            )

            show_main_menu(
                chat_id
            )

            return

        # ----------------------------------------------------
        # /UPDATE
        # ----------------------------------------------------

        if command == "/update":

            if not UPDATE_LOCK.acquire(
                blocking=False
            ):

                send_telegram(
                    chat_id,
                    "⏳ A home IPv6 update "
                    "is already running."
                )

                return

            send_telegram(
                chat_id,
                "⏳ Home IPv6 "
                "update started."
            )

            def manual_update_thread():

                try:

                    perform_home_update(
                        source="Manual",
                        chat_id=chat_id
                    )

                finally:

                    UPDATE_LOCK.release()

            threading.Thread(
                target=manual_update_thread,
                daemon=True
            ).start()

            return

        # ----------------------------------------------------
        # /STATUS
        # ----------------------------------------------------

        if command == "/status":

            threading.Thread(
                target=handle_status,
                args=(chat_id,),
                daemon=True
            ).start()

            return

        # ----------------------------------------------------
        # /LIST
        # ----------------------------------------------------

        if command == "/list":

            threading.Thread(
                target=handle_list,
                args=(chat_id,),
                daemon=True
            ).start()

            return

        # ----------------------------------------------------
        # /ADD
        # ----------------------------------------------------

        if command == "/add":

            if not argument:

                start_add_flow(
                    chat_id
                )

                return

            threading.Thread(
                target=handle_add,
                args=(
                    argument,
                    chat_id
                ),
                daemon=True
            ).start()

            return

        # ----------------------------------------------------
        # /DELETE
        # ----------------------------------------------------

        if command == "/delete":

            if not argument:

                show_delete_menu(
                    chat_id
                )

                return

            threading.Thread(
                target=handle_delete_command,
                args=(
                    argument,
                    chat_id
                ),
                daemon=True
            ).start()

            return

        # ----------------------------------------------------
        # UNKNOWN
        # ----------------------------------------------------

        send_telegram(
            chat_id,
            "❓ Unknown command.\n\n"
            "Use /start to open the bot menu."
        )

    except Exception as e:

        log(
            f"Message handler error: "
            f"{e}"
        )


# ============================================================
# TELEGRAM LONG POLLING
# ============================================================

def telegram_polling():

    log(
        "Telegram polling started"
    )

    offset = None

    while True:

        # IMPORTANT:
        # Explicitly request callback_query updates.
        #
        # Telegram remembers allowed_updates from previous
        # getUpdates calls, so this is deliberately specified
        # on EVERY polling request.

        payload = {
            "timeout": "10",
            "allowed_updates": [
                "message",
                "callback_query"
            ]
        }

        if offset is not None:

            payload["offset"] = str(
                offset
            )

        try:

            result = telegram_request(
                "getUpdates",
                payload,
                timeout=15
            )

            if not result:

                time.sleep(2)

                continue

            if not result.get(
                "ok"
            ):

                log(
                    "Telegram getUpdates "
                    f"failed: {result}"
                )

                time.sleep(2)

                continue

            updates = result.get(
                "result",
                []
            )

            if updates:

                log(
                    f"Telegram received "
                    f"{len(updates)} update(s)"
                )

            for update in updates:

                update_id = update.get(
                    "update_id"
                )

                if update_id is not None:

                    offset = (
                        update_id + 1
                    )

                # --------------------------------------------
                # Normal message
                # --------------------------------------------

                message = update.get(
                    "message"
                )

                if message:

                    threading.Thread(
                        target=handle_message,
                        args=(message,),
                        daemon=True
                    ).start()

                # --------------------------------------------
                # Inline button callback
                # --------------------------------------------

                callback = update.get(
                    "callback_query"
                )

                if callback:

                    log(
                        "Callback query received: "
                        f"{callback.get('data')}"
                    )

                    threading.Thread(
                        target=handle_callback,
                        args=(callback,),
                        daemon=True
                    ).start()

        except Exception as e:

            log(
                f"Telegram polling error: "
                f"{e}"
            )

            time.sleep(2)


# ============================================================
# AUTOMATIC CHECKER
# ============================================================

def automatic_checker():

    log(
        "Automatic checker started. "
        f"Interval={CHECK_INTERVAL}s"
    )

    # --------------------------------------------------------
    # Immediate startup check
    # --------------------------------------------------------

    try:

        if UPDATE_LOCK.acquire(
            blocking=False
        ):

            try:

                perform_home_update(
                    source="Automatic"
                )

            finally:

                UPDATE_LOCK.release()

        else:

            log(
                "Automatic check skipped because "
                "an update is already running."
            )

    except Exception as e:

        log(
            f"Automatic checker error: "
            f"{e}"
        )

    # --------------------------------------------------------
    # Periodic checks
    # --------------------------------------------------------

    while True:

        time.sleep(
            CHECK_INTERVAL
        )

        try:

            if not UPDATE_LOCK.acquire(
                blocking=False
            ):

                log(
                    "Automatic check skipped because "
                    "an update is already running."
                )

                continue

            try:

                perform_home_update(
                    source="Automatic"
                )

            finally:

                UPDATE_LOCK.release()

        except Exception as e:

            log(
                f"Automatic checker error: "
                f"{e}"
            )


# ============================================================
# MAIN
# ============================================================

def main():

    log("=" * 60)

    log(
        "Cloudflare List Automation Bot"
    )

    log("=" * 60)

    log(
        f"Config file: "
        f"{CONFIG_FILE}"
    )

    log(
        f"Cloudflare Account: "
        f"{CF_ACCOUNT_ID}"
    )

    log(
        f"Cloudflare List: "
        f"{CF_LIST_ID}"
    )

    log(
        f"Check interval: "
        f"{CHECK_INTERVAL}s"
    )

    log(
        "Allowed users: "
        + ", ".join(
            sorted(ALLOWED_USERS)
        )
    )

    log(
        f"HOME comment: "
        f"{HOME_COMMENT}"
    )

    log(
        f"CUSTOM comment: "
        f"{CUSTOM_COMMENT}"
    )

    log("=" * 60)

    threading.Thread(
        target=automatic_checker,
        daemon=True
    ).start()

    telegram_polling()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
