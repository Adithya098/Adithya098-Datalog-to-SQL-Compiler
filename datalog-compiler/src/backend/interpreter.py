from backend.sql_statement import *
from common.node_names import *
from backend.views import Views

class Interpreter:
    def __init__(self):
        self.tables_dic = {}
        self.views_dic = {}

    def get_node_name(self, tup):
        return tup[0]

    def get_value(self, node_val, tup, idx=1):
        assert tup[0] == node_val
        return tup[idx]

    def check_value_of_statement(self, statement):
        if self.get_node_name(statement) == ASSERTION_NODE:
            if self.traverse_and_get_value([ASSERTION_NODE, CLAUSE_NODE], statement) == ':-':
                return "INTERPRET_RULE" 
            return "CREATE_AND_INSERT"
        if self.get_node_name(statement) == QUERY_NODE:
            return "QUERY"
        return "UNSUPPORTED_STATEMENT"

    def traverse_and_get_value(self, list_of_node_names, node, list_of_idx=None):
        node_val = node
        for idx, node_name in enumerate(list_of_node_names):
            if list_of_idx is not None:
                node_val = self.get_value(node_name, node_val, list_of_idx[idx])
            else:
                node_val = self.get_value(node_name, node_val)
        return node_val
    
    def get_name_of_view_or_table(self, statement):
        if statement[0] == ASSERTION_NODE:
            return self.traverse_and_get_value(
                [ASSERTION_NODE, CLAUSE_NODE, LITERAL_NODE, PREDICATE_NODE],
                statement
            )
        return self.traverse_and_get_value(
            [LITERAL_NODE, PREDICATE_NODE],
            statement
        )
    
    def get_terms_of_view_or_table(self, statement):
        if statement[0] == ASSERTION_NODE:
            return self.traverse_and_get_value(
                [ASSERTION_NODE, CLAUSE_NODE, LITERAL_NODE, TERMS_NODE],
                statement,
                [1, 1, 3, 1]
            )
        return self.traverse_and_get_value(
            [LITERAL_NODE, TERMS_NODE],
            statement,
            [3, 1]
        )

    def interpret_create_and_insert_statement(self, statement):
        table_name = self.get_name_of_view_or_table(statement)
        terms = self.get_terms_of_view_or_table(statement)
        columns = []
        for term in terms:
            columns.append(self.traverse_and_get_value([TERM_NODE, CONSTANT_NODE], term))
        if table_name in self.tables_dic:
            return get_insert_statement(table_name, columns)
        self.tables_dic[table_name] = len(columns)
        return get_create_and_insert_statement(table_name, columns)
    
    def process_head_when_creating_view(self, head):
        view_name = self.get_name_of_view_or_table(head)
        terms_of_head = self.get_terms_of_view_or_table(head)
        columns_of_head = [
            self.get_value(TERM_NODE, term) for term in terms_of_head
        ]
        return view_name, columns_of_head
    
    def process_body_when_creating_view(self, body):
        body_dic = {}
        literals = self.get_value(BODY_NODE, body)
        for literal in literals:
            table_or_view_name = self.get_name_of_view_or_table(literal)
            terms = self.get_terms_of_view_or_table(literal)
            columns_of_head = [
                self.get_value(TERM_NODE, term) for term in terms
            ]
            body_dic[table_or_view_name] = columns_of_head
        return body_dic
    
    def validate_view_graph(self, columns_of_view, body_dic):
        unreferenced_column = set(columns_of_view)
        referenced_column = set()
        for table_or_view_name, cols in body_dic.items():
            if table_or_view_name not in self.tables_dic and table_or_view_name not in self.views_dic:
                raise Exception("Referencing a view or table not created previously")
            for col in cols:
                if col in unreferenced_column:
                    referenced_column.add(col)
        assert unreferenced_column.difference(referenced_column) == set()

    
    def create_view_graph(self, statement):
        # Views will be lazily created when they are queried
        head = self.get_value(ASSERTION_NODE, statement)[2]
        body = self.get_value(ASSERTION_NODE, statement)[3]
        view_name, columns_of_view = self.process_head_when_creating_view(head)
        body_dic = self.process_body_when_creating_view(body)
        self.validate_view_graph(columns_of_view, body_dic)
        if view_name in self.views_dic:
            view = self.views_dic[view_name]
            assert view.cols == columns_of_view
            view.bodies.append(body_dic)
        else:
            self.views_dic[view_name] = Views(view_name, columns_of_view, False, [body_dic])

    def interpret_creation_of_view(self, view_name):
        statements = []
        view = self.views_dic[view_name]
        if view.is_executed:
            statements.extend(get_drop_view_statement(view_name))
        for body in view.bodies:
            for dependent_table_or_view_name in body.keys():
                if dependent_table_or_view_name == view_name:
                    continue
                if dependent_table_or_view_name in self.tables_dic:
                    continue
                if dependent_table_or_view_name in self.views_dic:
                    if not self.views_dic[dependent_table_or_view_name].is_executed:
                        statements.extend(self.interpret_creation_of_view(dependent_table_or_view_name))
                    continue
                # Shouldn't reached here
                raise Exception("Referencing a view or table not created previously")
        statements.extend(create_view_statement(view))
        view.is_executed = True
        return statements
    
    def interpret_query_statement(self, statement):
        statements = []
        table_or_view_name = self.traverse_and_get_value(
            [QUERY_NODE, LITERAL_NODE, PREDICATE_NODE],
            statement
        )
        if table_or_view_name in self.views_dic:
            statements.extend(self.interpret_creation_of_view(table_or_view_name)) 
        if table_or_view_name in self.tables_dic:
            len_of_columns = self.tables_dic[table_or_view_name]
        else:
            len_of_columns = len(self.views_dic[table_or_view_name].cols)
        terms = self.traverse_and_get_value(
            [QUERY_NODE, LITERAL_NODE, TERMS_NODE],
            statement,
            [1, 3, 1]
        )
        assert len(terms) == len_of_columns
        constraints = {}
        for i in range(len_of_columns):
            term = self.get_value(TERM_NODE, terms[i])
            if type(term) is tuple:
                constraints[i] = (self.get_value(CONSTANT_NODE, term))
        statements.extend(get_basic_query_statement(table_or_view_name, constraints))
        return statements

    def interpret_statements(self, statements):
        sql_translations = []
        for statement_node, statement in statements:
            assert statement_node == STATEMENT_NODE
            type_of_statement = self.check_value_of_statement(statement)
            if type_of_statement == "CREATE_AND_INSERT":
                sql_translations.extend(self.interpret_create_and_insert_statement(statement))
            elif type_of_statement == "INTERPRET_RULE":
                self.create_view_graph(statement)
            elif type_of_statement == "QUERY":
                sql_translations.extend(self.interpret_query_statement(statement))
            else:
                raise Exception("Unsupported statement")
        return sql_translations

    def interpret(self, ast):
        assert self.get_node_name(ast) == PROGRAM_NODE
        return self.interpret_statements(ast[1])
