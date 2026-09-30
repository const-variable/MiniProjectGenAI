# Online LangGraph

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	condense(condense)
	retrieve(retrieve)
	select_tables(select_tables)
	generate_sql(generate_sql)
	check_and_execute(check_and_execute)
	fix_sql(fix_sql)
	answer(answer)
	__end__([<p>__end__</p>]):::last
	__start__ -.-> condense;
	__start__ -.-> generate_sql;
	__start__ -.-> retrieve;
	check_and_execute -.-> answer;
	check_and_execute -.-> fix_sql;
	condense -.-> generate_sql;
	condense -.-> retrieve;
	fix_sql --> check_and_execute;
	generate_sql --> check_and_execute;
	retrieve --> select_tables;
	select_tables --> generate_sql;
	answer --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

The start edge chooses between retrieval and SQL generation. Supplying `tables_override` bypasses `retrieve` and `select_tables`; failed SQL routes through `fix_sql` until it succeeds or the retry limit is reached.
