import requests
import frappe
from frappe import _
from frappe.model.document import Document

_DEFAULT_AGENT_SERVER_URL: str = "http://127.0.0.1:8010"


def _load_env() -> None:
	try:
		import os
		app_root = os.path.abspath(os.path.join(frappe.get_app_path("accountant_agent"), ".."))
		env_path = os.path.join(app_root, ".env")
		if os.path.exists(env_path):
			with open(env_path, "r", encoding="utf-8") as f:
				for line in f:
					line = line.strip()
					if not line or line.startswith("#"):
						continue
					if "=" in line:
						key, val = line.split("=", 1)
						key = key.strip()
						val = val.strip()
						if val.startswith(('"', "'")) and val.endswith(val[0]):
							val = val[1:-1]
						os.environ.setdefault(key, val)
	except Exception:
		pass


def get_agent_server_url() -> str:
	"""Base URL of the platform's agent API for this site."""
	import os
	_load_env()
	return (
		frappe.conf.get("accountant_agent_server_url")
		or os.environ.get("ACCOUNTANT_AGENT_SERVER_URL")
		or _DEFAULT_AGENT_SERVER_URL
	).rstrip("/")


def decode_jwt_payload(token: str) -> dict:
	"""
	Decodes the JWT token payload without validating the signature.
	Returns the payload dictionary, or an empty dictionary if invalid.
	"""
	import base64
	import json
	try:
		parts = token.split(".")
		if len(parts) == 3:
			payload_b64 = parts[1]
			# Add base64 padding
			payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
			payload_json = base64.urlsafe_b64decode(payload_b64).decode("utf-8")
			return json.loads(payload_json)
	except Exception as e:
		frappe.log_error(f"JWT decode error: {str(e)}", "Accountant Agent JWT Decode")
	return {}


class AgentSettings(Document):
	pass


@frappe.whitelist()
def get_agent_settings_name(email):
	"""Returns the document name of Agent Settings for the given email."""
	if not email:
		return None
	return frappe.db.get_value("Agent Settings", {"email": email}, "name")


@frappe.whitelist()
def get_user_usage(email):
	"""Fetches usage statistics from backend agent server for given email or doc name."""
	if not email:
		return {"daily_usage_percentage": 0.0, "total_usage_percentage": 0.0}

	doc = None
	if frappe.db.exists("Agent Settings", email):
		doc = frappe.get_doc("Agent Settings", email)
	else:
		doc_name = frappe.db.get_value("Agent Settings", {"email": email}, "name")
		if doc_name:
			doc = frappe.get_doc("Agent Settings", doc_name)

	if not doc:
		return {"daily_usage_percentage": 0.0, "total_usage_percentage": 0.0}

	access_token = doc.get_password("access_token")
	user_id = None
	if access_token:
		payload = decode_jwt_payload(access_token)
		user_id = payload.get("sub")

	# Fallback to api_key for legacy users
	if not user_id:
		user_id = doc.get_password("api_key")

	if not user_id:
		return {"daily_usage_percentage": 0.0, "total_usage_percentage": 0.0}

	try:
		response = requests.get(f"{get_agent_server_url()}/users/{user_id}/usage", timeout=10)
		if response.status_code == 200:
			data = response.json()
			return {
				"daily_usage_percentage": round(data.get("daily_usage_percentage", 0.0), 1),
				"total_usage_percentage": round(data.get("total_usage_percentage", 0.0), 1)
			}
	except Exception as e:
		frappe.log_error(f"Error fetching user usage: {str(e)}", "Accountant Agent Usage Fetch")

	return {"daily_usage_percentage": 0.0, "total_usage_percentage": 0.0}
