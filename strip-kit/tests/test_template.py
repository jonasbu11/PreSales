"""Static checks on template.yaml: IAM scope and data-safety properties.
python3 tests/test_template.py
"""
import pathlib
import yaml


class CfnLoader(yaml.SafeLoader):
    pass


def _tag(loader, suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return {suffix: loader.construct_scalar(node)}
    if isinstance(node, yaml.SequenceNode):
        return {suffix: loader.construct_sequence(node)}
    return {suffix: loader.construct_mapping(node)}


CfnLoader.add_multi_constructor("!", lambda l, s, n: _tag(l, s, n))

doc = yaml.load(open(pathlib.Path(__file__).parent.parent / "template.yaml"), Loader=CfnLoader)
res = doc["Resources"]
fn = res["Function"]["Properties"]
stmts = [st for pol in fn["Policies"] for st in pol.get("Statement", [])]
assert not any("DynamoDBCrudPolicy" in pol for pol in fn["Policies"]), "managed CRUD policy grants Delete and Scan"

ddb = [st for st in stmts if any(a.startswith("dynamodb:") for a in st["Action"])]
assert len(ddb) == 1, ddb
assert set(ddb[0]["Action"]) == {"dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query", "dynamodb:UpdateItem"}, ddb[0]["Action"]
assert ddb[0]["Resource"] == {"GetAtt": ["Table", "Arn"]} or ddb[0]["Resource"] == {"GetAtt": "Table.Arn"}, ddb[0]["Resource"]
print("ok: dynamodb statement is explicit and excludes Delete/Scan")

tbl = res["Table"]
assert tbl.get("DeletionPolicy") == "Retain" and tbl.get("UpdateReplacePolicy") == "Retain", \
    "a stack delete or key-schema replace would destroy the calibration history"
print("ok: table is retained on stack delete and replace")

rce = fn.get("ReservedConcurrentExecutions")
assert isinstance(rce, int) and 1 <= rce <= 10, f"concurrent Bedrock fan-out is unbounded: ReservedConcurrentExecutions={rce}"
print(f"ok: function concurrency capped at {rce}")

bedrock = [st for st in stmts if any(a.startswith("bedrock:") for a in st["Action"])]
assert len(bedrock) == 1, bedrock
for r in bedrock[0]["Resource"]:
    arn = r["Sub"] if isinstance(r, dict) else r
    assert isinstance(arn, str) and arn.startswith("arn:aws:bedrock:"), arn
    region = arn.replace("${AWS::Region}", "REGION").split(":")[3]
    assert region == "REGION", f"Bedrock statement grants a wildcard region: {arn}"
fm = [(r["Sub"] if isinstance(r, dict) else r) for r in bedrock[0]["Resource"] if "foundation-model" in str(r)]
assert fm == ["arn:aws:bedrock:${AWS::Region}::foundation-model/*"], fm
print("ok: bedrock statement is scoped to the stack region")

print("template checks passed")
