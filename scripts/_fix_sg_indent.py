"""Dedent the body of _check_aws_sg_open_cidr and add boolean helpers."""

path = "cna/ai_engine/analysis_engine.py"
with open(path, encoding="utf-8") as f:
    src = f.read()

# The body after the three fp/tp/proto lines is still indented 16 spaces (was inside for cidr loop).
# We need it at 8 spaces.  Find the section from "        if proto == \"-1\":" to just before
# "    def _check_aws_tgw" and dedent by 8 spaces.

OLD = """\
    def _check_aws_sg_open_cidr(self, sg, vpc, account_id: str, region: str, rule, cidr: str) -> None:
        fp = rule.from_port
        tp = rule.to_port
        proto = rule.protocol

                if proto == "-1":"""

# Find the exact block: from the new method def to "    def _check_aws_tgw"
start_marker = "    def _check_aws_sg_open_cidr(self, sg, vpc, account_id: str, region: str, rule, cidr: str) -> None:\n"
end_marker = "\n    def _check_aws_tgw("

start_idx = src.index(start_marker)
end_idx = src.index(end_marker, start_idx)

# Extract the block (excluding end_marker)
block = src[start_idx:end_idx]

# Dedent the "if" lines (currently 16 spaces → should be 8 spaces)
# The method header + 3 var lines are at 4/8 spaces already; the problem is lines that are 16+ spaces
lines = block.split("\n")
fixed_lines = []
for line in lines:
    if line.startswith("                "):  # 16 spaces
        line = line[8:]  # dedent by 8
    fixed_lines.append(line)
fixed_block = "\n".join(fixed_lines)

# Also fix the two multi-operand boolean conditions, adding a _tcp_port_exposed helper
# Insert helper before the new method
helper = '''    @staticmethod
    def _tcp_port_exposed(proto: str, fp, tp, port: int) -> bool:
        """Return True if a TCP rule exposes the given port."""
        return proto in ("tcp", "6") and fp is not None and fp <= port <= (tp or fp)

'''

# Replace SSH and RDP inline conditions
fixed_block = fixed_block.replace(
    'if proto in ("tcp", "6") and fp is not None and fp <= _PORT_SSH <= (tp or fp):',
    "if self._tcp_port_exposed(proto, fp, tp, _PORT_SSH):",
)
fixed_block = fixed_block.replace(
    'if proto in ("tcp", "6") and fp is not None and fp <= _PORT_RDP <= (tp or fp):',
    "if self._tcp_port_exposed(proto, fp, tp, _PORT_RDP):",
)

# Replace the block in src
new_src = src[:start_idx] + helper + fixed_block + src[end_idx:]

with open(path, "w", encoding="utf-8") as f:
    f.write(new_src)

print("Done")
