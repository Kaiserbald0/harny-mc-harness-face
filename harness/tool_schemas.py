READ_FILE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a text file inside the sandbox. Returns its contents (capped at 4000 chars).",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to sandbox root."},
            },
            "required": ["path"],
        },
    },
}

WRITE_FILE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "Write text to a file inside the sandbox. Creates parent dirs.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
}

LIST_DIR_SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_dir",
        "description": "List entries of a directory inside the sandbox.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": "."},
            },
        },
    },
}

ALL_TOOL_SCHEMAS = [READ_FILE_SCHEMA, WRITE_FILE_SCHEMA, LIST_DIR_SCHEMA]