from tree_sitter import Language, Parser
import tree_sitter_javascript


language = Language(tree_sitter_javascript.language())
parser = Parser(language)

source_code = b"""
const name = "Aysha";

function greet(user) {
    console.log(user);
}

greet(name);
"""

tree = parser.parse(source_code)

print(tree.root_node)