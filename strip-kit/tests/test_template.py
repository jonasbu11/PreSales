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

print("template checks passed")
