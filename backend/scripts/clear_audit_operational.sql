-- Clear processing history while keeping domain / seed data intact.
-- Preserves: tickets, customers, orders, products, knowledge_base
-- Removes: audit rows, cost rows, DLQ rows (re-runnable demos)

BEGIN;

DELETE FROM dead_letter_queue;
DELETE FROM cost_tracking;
DELETE FROM ticket_audit;

COMMIT;
