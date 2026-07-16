def _patch_trie_rule(trie_rule, prefix_key: str) -> None:
    if getattr(trie_rule, "_elysia_empty_message_patch", False):
        return

    original_get_value = trie_rule.get_value

    def get_value(cls, bot, event, state):
        if event.get_type() == "message" and not event.get_message():
            prefix = {
                "command": None,
                "raw_command": None,
                "command_arg": None,
                "command_start": None,
                "command_whitespace": None,
            }
            state[prefix_key] = prefix
            return prefix
        return original_get_value(bot, event, state)

    trie_rule.get_value = classmethod(get_value)
    trie_rule._elysia_empty_message_patch = True


def patch_empty_message_command_parsing() -> None:
    """Guard NoneBot's command trie against valid QQ events with no segments."""
    from nonebot.consts import PREFIX_KEY
    from nonebot.rule import TrieRule

    _patch_trie_rule(TrieRule, PREFIX_KEY)
