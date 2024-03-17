from frontend import parser
from backend import interpreter
import traceback

def generate_sql_query_from_datalog_query(datalog_query):
    ast = parser.parse(datalog_query)
    sql_statements = interpreter.interpret(ast)
    for sql_statement in sql_statements:
        print(sql_statement)

if __name__ == "__main__":
    while True:
        try:
            # datalog_query = input('What is the datalog query?\n')
            datalog_query = '''
            s(x, y).
            '''
            res = generate_sql_query_from_datalog_query(datalog_query)
            # Temporarily disabling the REPL
            break
        except KeyboardInterrupt:
            print("Quitting")
            break
        except Exception:
            traceback.print_exc()
            break
