"""The attack codes this layer answers (the PSE guard reference Sec 15, basic layer).

Codes and names: Haddix, J. (2026). Arcanum Prompt Injection Taxonomy (v1.6.1).
Arcanum Information Security. https://www.arcanum-sec.com/pitax (CC BY 4.0).
"""

ATTRIBUTION = ("Haddix, J. (2026). Arcanum Prompt Injection Taxonomy (v1.6.1). "
               "Arcanum Information Security. https://www.arcanum-sec.com/pitax (CC BY 4.0)")

NORMALIZATION = {
    "PIT-E-11": "Braille",
    "PIT-E-12": "Bubble/Enclosed Text",
    "PIT-E-13": "Case Changing",
    "PIT-E-19": "Fullwidth",
    "PIT-E-20": "Homoglyphs",
    "PIT-E-23": "Invisible Text",
    "PIT-E-28": "Metacharacter Confusion",
    "PIT-E-29": "Mathematical Unicode",
    "PIT-E-34": "Regional Indicators",
    "PIT-E-37": "Spaces/Whitespace",
    "PIT-E-38": "Splats",
    "PIT-E-40": "Small Caps/Sub/Superscript",
    "PIT-E-43": "Strikethrough/Underline/Overlay",
    "PIT-E-45": "Upside Down",
    "PIT-E-47": "Vertical Text",
    "PIT-E-49": "Wingdings/Symbol Fonts",
    "PIT-E-51": "Zalgo",
    "PIT-E-54": "Bidirectional Override",
    "PIT-E-59": "ANSI Escape Concealment",
}
DECODERS = {
    "PIT-E-01": "A1Z26",
    "PIT-E-06": "Baconian",
    "PIT-E-07": "Base64",
    "PIT-E-08": "Binary",
    "PIT-E-21": "Hexadecimal",
    "PIT-E-22": "HTML Entities",
    "PIT-E-30": "Morse",
    "PIT-E-31": "NATO Phonetic",
    "PIT-E-33": "Rail Fence",
    "PIT-E-36": "Reverse",
    "PIT-E-44": "Tap Code",
    "PIT-E-46": "URL Encoding",
    "PIT-E-55": "Alternative Base Encodings",
    "PIT-E-56": "Numeric Code-Point",
    "PIT-E-57": "Layered Encoding",
    "PIT-E-58": "Compression Encoding",
    "PIT-E-62": "Legacy Charset",
}
STRUCTURE = {
    "PIT-E-18": "Graph Nodes",
    "PIT-E-25": "JSON",
    "PIT-E-27": "Markdown",
    "PIT-E-50": "XML",
}
CONTROL_TOKENS = {
    "PIT-T-07": "End Sequences",
    "PIT-T-48": "Special-Token Injection",
}

BASIC_LAYER = {**NORMALIZATION, **DECODERS, **STRUCTURE, **CONTROL_TOKENS}
assert len(BASIC_LAYER) == 42, len(BASIC_LAYER)

GROUP = {**{c: "normalization" for c in NORMALIZATION}, **{c: "decoder" for c in DECODERS},
         **{c: "structure" for c in STRUCTURE}, **{c: "control_token" for c in CONTROL_TOKENS}}

# Surface signals Vid also shows (not Arcanum PIT codes).
SIGNALS = {
    "SIG-ACROSTIC": "Acrostic (hidden in first letters)",
    "SIG-TRANSFORM-EXEC": "Transform-and-execute instruction",
}
ALL_NAMES = {**BASIC_LAYER, **SIGNALS}
