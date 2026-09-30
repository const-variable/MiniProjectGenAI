-- Example SQL query log for the sample data.
-- Upload this as "query logs" together with orders.csv, products.csv,
-- students.csv and scores.csv. Table names = file names without extension.

-- Monthly revenue trend
SELECT strftime('%Y-%m', order_date) AS month, SUM(revenue) AS revenue
FROM orders
GROUP BY month
ORDER BY month;

-- Revenue by product category
SELECT p.category, SUM(o.revenue) AS revenue
FROM orders o JOIN products p ON o.product_id = p.product_id
GROUP BY p.category
ORDER BY revenue DESC;

-- Quarterly revenue by category
SELECT p.category,
       strftime('%Y', o.order_date) || '-Q' || ((CAST(strftime('%m', o.order_date) AS INTEGER) + 2) / 3) AS quarter,
       SUM(o.revenue) AS revenue
FROM orders o JOIN products p ON o.product_id = p.product_id
GROUP BY p.category, quarter;

-- Orders and units by region
SELECT region, COUNT(*) AS orders, SUM(units) AS units
FROM orders
GROUP BY region;

-- Best-selling products by units
SELECT p.product_name, SUM(o.units) AS units
FROM orders o JOIN products p ON o.product_id = p.product_id
GROUP BY p.product_name
ORDER BY units DESC
LIMIT 5;

-- Average score by subject and term
SELECT subject, term, ROUND(AVG(score), 2) AS avg_score
FROM scores
GROUP BY subject, term;

-- Average score by school
SELECT st.school, ROUND(AVG(sc.score), 2) AS avg_score
FROM scores sc JOIN students st ON sc.student_id = st.student_id
GROUP BY st.school;

-- Number of students per grade
SELECT grade, COUNT(*) AS students
FROM students
GROUP BY grade;
