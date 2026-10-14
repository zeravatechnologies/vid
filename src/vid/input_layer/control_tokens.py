"""Removal of the model's control tokens and end sequences, and their near
neighbours, from any input that is not the system's own
(the PSE guard reference Sec 3). Codes T-07 (end sequences) and T-48 (special
tokens)."""

from __future__ import annotations

import re

from vid.input_layer.types import Finding, short

_END_NAMES = r"(?:im_end|endoftext|end_of_text|eot_id|eom_id|end|eos|stop|return|endofprompt|end_of_turn|im_sep)"
# Pipe tokens in any spacing or case: <|im_end|>, < | IM_END | >, <|im_end>, <im_end|>
_PIPE_TOKEN = re.compile(r"<\s*\|\s*([A-Za-z][\w\-]{1,40})\s*\|?\s*>|<\s*([A-Za-z][\w\-]{1,40})\s*\|\s*>")
_OTHER_SPECIAL = re.compile(
    r"\[\s*/?\s*INST\s*\]|<<\s*/?\s*SYS\s*>>|<\s*/?\s*(?:start_of_turn|end_of_turn)\s*>|<\s*(?:bos|eos)\s*>"
    r"|<\s*/?\s*(?:system|assistant|tool_call|tool_response|im_start|im_end)\s*>"
    r"|<\s*reserved_special_token_\d+\s*>",
    re.I)
# Legacy turn markers that end the user's turn ("\n\nHuman:", "\n\nAssistant:")
_TURN = re.compile(r"(?:^|\n)\s*\n\s*(Human|Assistant)\s*:", re.I)
_EOS_S = re.compile(r"</s>")


def remove(text: str) -> tuple[str, list[Finding]]:
    ends, specials = [], []

    def pipe(m: re.Match) -> str:
        name = (m.group(1) or m.group(2)).lower()
        (ends if re.fullmatch(_END_NAMES, name) else specials).append(m.group(0))
        return " "

    out = _PIPE_TOKEN.sub(pipe, text)

    def other(m: re.Match) -> str:
        tok = re.sub(r"\s", "", m.group(0).lower())
        (ends if tok in ("[/inst]", "<</sys>>", "</start_of_turn>", "<end_of_turn>", "<eos>", "</assistant>", "</system>", "<im_end>", "</im_start>") else specials).append(m.group(0))
        return " "

    out = _OTHER_SPECIAL.sub(other, out)

    def turn(m: re.Match) -> str:
        ends.append(m.group(0).strip())
        return "\n" + m.group(1) + " said:"   # keep the words, drop the turn boundary

    out = _TURN.sub(turn, out)
    # "</s>" ends a turn for many models; a lone one (not closing an HTML <s>) is an end sequence.
    if _EOS_S.search(out) and out.count("<s>") < out.count("</s>"):
        ends += _EOS_S.findall(out)
        out = _EOS_S.sub(" ", out)

    findings = []
    if ends:
        findings.append(Finding("PIT-T-07", f"{len(ends)} end-of-turn sequence(s) removed ({', '.join(sorted(set(ends))[:4])}).",
                                short(text), short(out), count=len(ends)))
    if specials:
        findings.append(Finding("PIT-T-48", f"{len(specials)} special token(s) of a model's chat format removed ({', '.join(sorted(set(specials))[:4])}).",
                                short(text), short(out), count=len(specials)))
    return (re.sub(r"[ \t]{2,}", " ", out) if findings else text), findings
