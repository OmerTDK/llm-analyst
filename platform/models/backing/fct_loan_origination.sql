-- Pass-through view over the fixture's dwh schema.
-- The semantic YAML files reference this model via ref(); the DuckDB fixture
-- already contains the materialized table from credit-data-platform.
select *
from dwh.fct_loan_origination
