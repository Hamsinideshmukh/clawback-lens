-- Runs once, on the first start of the compose database: a separate database
-- for the test suite, which drops and recreates its schema on every run.
CREATE DATABASE clawback_test OWNER clawback;
