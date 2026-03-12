from typing import Optional
import base64

from logs import taglog

class ServiceConfig:
    def __init__(
        self, 
        service: str,
        enabled: bool,
        username: Optional[str] = None,
        password: Optional[str] = None):
        self.service = service
        self.enabled = enabled
        self.username = username

        if password and password.strip():
            try:
                decoded_bytes = base64.b64decode(password.encode("utf-8"))
                self.password = decoded_bytes.decode("utf-8")
            except Exception as e:
                # Assume already plain text if decoding fails
                taglog("CONFIG", f"Password decode failed, using raw password: {e}")
                self.password = password
        else:
            self.password = None

    def json(self) -> dict:
        obj = {}
        obj["enabled"] = self.enabled

        if self.username:
            obj["username"] = self.username

        if self.password:
            # Ensure encoded password when we make json dict so it's always stored as
            # encoded string
            encoded = base64.b64encode(self.password.encode("utf-8")).decode("utf-8")
            obj["password"] = encoded

        return obj

    def enable(self, username, password):
        self.enabled = True
        self.password = password
        
        sanitized = username.strip()

        # for Bluesky we always want a full @username.bsky.social address
        if self.service == "bluesky":
            if not sanitized.startswith("@"):
                sanitized = "@" + sanitized

            if not sanitized.endswith(".bsky.social"):
                sanitized = sanitized + ".bsky.social"
                
        self.username = sanitized

