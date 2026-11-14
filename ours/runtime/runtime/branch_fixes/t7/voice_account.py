"""Explicit per-account credentials and one-session lease; no secret serialization."""

from __future__ import annotations

import copy
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VoiceAccount:
    label: str
    credential_file: Path
    lease_file: Path
    independence: str

    @classmethod
    def load(cls, path: Path) -> VoiceAccount:
        config = json.loads(path.read_text())
        if config["schema"] != "t7_voice_account_v1":
            raise ValueError("Unsupported voice account configuration")
        if config["max_simultaneous_sessions"] != 1:
            raise ValueError("One session per account remains required")
        if (
            config["model"] != "qwen3.8-omni-flash-realtime"
            or config["voice"] != "Tina"
        ):
            raise ValueError("Account isolation must not change model or voice")
        key = Path(config["credential_file"])
        lease = Path(config["lease_file"])
        if not key.is_absolute() or not lease.is_absolute():
            raise ValueError("Credential and account lease paths must be absolute")
        metadata = key.stat()
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise PermissionError(
                "Credential must be owned and readable only by the user"
            )
        if not key.read_text().strip():
            raise ValueError("Empty voice credential")
        if not lease.parent.is_dir():
            raise ValueError("Prepare the private account lease directory explicitly")
        descriptor = os.open(lease, os.O_RDWR | os.O_CREAT, 0o600)
        os.close(descriptor)
        return cls(config["label"], key, lease, config["independence"])

    def credential(self) -> str:
        return self.credential_file.read_text().strip()

    def configure_providers(self, base: dict) -> dict:
        output = copy.deepcopy(base)
        # Explicit per-role apiKeyFile takes precedence over the legacy env key.
        # Changing DASHSCOPE_API_KEY alone would silently retain account A.
        for role in ("dialogue", "visual_qa", "speech"):
            provider = output["providers"][role]
            if provider["provider"] != "qwen-realtime":
                raise ValueError("Unexpected cloud role provider: " + role)
            provider["apiKeyFile"] = str(self.credential_file)
            provider.pop("apiKey", None)
        return output

    def public_metadata(self) -> dict:
        return dict(
            label=self.label,
            credential_source="private_file",
            lease_file=str(self.lease_file),
            account_independence=self.independence,
            simultaneous_sessions_per_account=1,
            shared_agent_model_compute=True,
        )
