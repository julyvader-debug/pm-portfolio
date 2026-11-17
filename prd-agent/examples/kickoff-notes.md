# Kickoff: promo stacking rules (fictional example)

Attendees: Pricing Lead, Pricing Manager, Pricing Ops, 2 engineers, PM

- Today promos are entered one at a time. When two promos apply to the same SKU,
  the system applies both, and nobody sees the combined discount until an order
  comes in.
- Pricing Lead: last quarter we had several orders where stacked promos pushed the
  price below cost. Finance caught them after the fact.
- We want a rule: a SKU can have only one active promo per channel, unless the
  promo is marked "stackable".
- Pricing Manager wants a warning at promo setup if the combined discount would
  push margin below the category floor.
- Margin floors by category exist in a spreadsheet today; not in the tool.
- Engineering: promos table has start and end dates but no channel field.
- Pricing Ops asked for a report of all overlapping promos, weekly.
- Nobody knew how many promos are active right now. Engineering will pull a count.
