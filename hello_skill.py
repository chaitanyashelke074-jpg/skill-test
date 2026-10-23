PLUGIN = {
    "name": "hello_skill",
    "description": "Says hello. Use when the user asks the hello skill to greet them.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

def run(parameters, player=None, session_memory=None):
    return "Hello from the installed skill, sir."
