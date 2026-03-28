"""Seed the legal reference database with sample precedents and laws."""

from pathlib import Path

from backend.legal_db.models import Law, Precedent
from backend.legal_db.store import LegalStore

SAMPLE_PRECEDENTS: list[Precedent] = [
    Precedent(
        case_name="Hadley v Baxendale",
        jurisdiction="England",
        year=1854,
        summary=(
            "Established the foreseeability rule for contract damages: damages must arise "
            "naturally from the breach or be within the contemplation of both parties at "
            "the time of contract formation."
        ),
        full_text=(
            "The court held that the plaintiff could not recover lost profits from mill "
            "downtime because the defendant was not informed of special circumstances. "
            "Damages for breach of contract are limited to those that arise naturally or "
            "were reasonably foreseeable by both parties."
        ),
        tags=["contract", "damages", "foreseeability", "breach"],
        outcome="Defendant not liable for unforeseeable consequential damages",
    ),
    Precedent(
        case_name="Donoghue v Stevenson",
        jurisdiction="United Kingdom",
        year=1932,
        summary=(
            "Established the modern concept of negligence and the neighbor principle: "
            "manufacturers owe a duty of care to end consumers."
        ),
        full_text=(
            "Mrs Donoghue consumed ginger beer containing a decomposed snail. The House "
            "of Lords held that the manufacturer owed a duty of care to consumers, "
            "establishing the neighbor principle: one must take reasonable care to avoid "
            "acts or omissions that could foreseeably harm persons closely affected."
        ),
        tags=["negligence", "duty of care", "tort", "product liability"],
        outcome="Manufacturer liable for negligence to end consumer",
    ),
    Precedent(
        case_name="Carlill v Carbolic Smoke Ball Company",
        jurisdiction="England",
        year=1893,
        summary=(
            "Unilateral offer to the world at large can form a binding contract. "
            "Performance of conditions constitutes acceptance."
        ),
        full_text=(
            "The defendant advertised a reward for anyone who used their smoke ball and "
            "still contracted influenza. The court held this was a valid unilateral offer "
            "and Mrs Carlill accepted by performing the conditions. The deposit showed "
            "sincerity of the offer."
        ),
        tags=["contract", "offer", "acceptance", "unilateral contract"],
        outcome="Binding unilateral contract; plaintiff awarded damages",
    ),
    Precedent(
        case_name="Smith v Hughes",
        jurisdiction="England",
        year=1871,
        summary=(
            "Objective test for contract formation: agreement is judged by outward "
            "appearance, not subjective intent."
        ),
        full_text=(
            "The buyer intended to purchase old oats but received new oats. The court "
            "held that contract formation depends on what a reasonable person would "
            "understand from the parties' words and conduct, not their private intentions."
        ),
        tags=["contract", "formation", "objective test", "intent"],
        outcome="Objective standard applies to contract formation",
    ),
    Precedent(
        case_name="Rylands v Fletcher",
        jurisdiction="England",
        year=1868,
        summary=(
            "Strict liability for non-natural use of land: a person who brings something "
            "likely to cause mischief onto their land is liable if it escapes."
        ),
        full_text=(
            "The defendant built a reservoir on his land. Water escaped through old mine "
            "shafts and flooded the plaintiff's mines. The House of Lords held the "
            "defendant strictly liable for the escape of water brought onto the land "
            "for non-natural use."
        ),
        tags=["strict liability", "tort", "land use", "nuisance"],
        outcome="Strict liability imposed for escape of dangerous things from land",
    ),
    Precedent(
        case_name="Marbury v Madison",
        jurisdiction="United States",
        year=1803,
        summary=(
            "Established judicial review: the Supreme Court has the power to declare "
            "acts of Congress unconstitutional."
        ),
        full_text=(
            "William Marbury petitioned the Supreme Court for a writ of mandamus. "
            "Chief Justice Marshall held that while Marbury had a right to his commission, "
            "the Court could not issue the writ because Section 13 of the Judiciary Act "
            "was unconstitutional, establishing the principle of judicial review."
        ),
        tags=["constitutional", "judicial review", "separation of powers"],
        outcome="Established judicial review; Judiciary Act Section 13 struck down",
    ),
    Precedent(
        case_name="Brown v Board of Education",
        jurisdiction="United States",
        year=1954,
        summary=(
            "Racial segregation in public schools violates the Equal Protection Clause "
            "of the Fourteenth Amendment."
        ),
        full_text=(
            "The Supreme Court unanimously held that separate educational facilities are "
            "inherently unequal and violate the Equal Protection Clause. This overturned "
            "Plessy v Ferguson's separate but equal doctrine in the context of public education."
        ),
        tags=["constitutional", "equal protection", "civil rights", "education"],
        outcome="Segregation in public schools declared unconstitutional",
    ),
    Precedent(
        case_name="Palsgraf v Long Island Railroad",
        jurisdiction="United States",
        year=1928,
        summary=(
            "Duty of care in negligence is owed only to foreseeable plaintiffs. "
            "Proximate cause requires foreseeability of harm to the specific plaintiff."
        ),
        full_text=(
            "A passenger dropped a package of fireworks while boarding a train. The "
            "resulting explosion knocked over scales that injured Mrs Palsgraf. The court "
            "held the railroad was not liable because the harm to Mrs Palsgraf was not a "
            "foreseeable consequence of the employee's conduct."
        ),
        tags=["negligence", "proximate cause", "foreseeability", "tort"],
        outcome="No liability; plaintiff was unforeseeable",
    ),
    Precedent(
        case_name="Victoria Laundry v Newman Industries",
        jurisdiction="England",
        year=1949,
        summary=(
            "Refined the remoteness of damages rule: damages recoverable if they were "
            "reasonably foreseeable as a serious possibility."
        ),
        full_text=(
            "Newman Industries delivered a boiler late to Victoria Laundry. The laundry "
            "claimed for lost ordinary profits and lost lucrative government contracts. "
            "The court held that ordinary profit loss was foreseeable but the exceptionally "
            "lucrative contracts were not, as Newman was unaware of them."
        ),
        tags=["contract", "damages", "remoteness", "foreseeability"],
        outcome="Ordinary lost profits recoverable; exceptional profits not foreseeable",
    ),
    Precedent(
        case_name="Central London Property Trust v High Trees House",
        jurisdiction="England",
        year=1947,
        summary=(
            "Established promissory estoppel: a promise intended to be binding and acted "
            "upon is enforceable even without consideration."
        ),
        full_text=(
            "During WWII, the landlord agreed to halve the rent on a block of flats. "
            "After the war, the landlord sought to restore full rent. Denning J held that "
            "the wartime promise was binding during the war years by estoppel, though full "
            "rent could be restored going forward."
        ),
        tags=["contract", "estoppel", "promissory estoppel", "consideration"],
        outcome="Promissory estoppel prevented enforcement of full rent during war period",
    ),
    Precedent(
        case_name="Miranda v Arizona",
        jurisdiction="United States",
        year=1966,
        summary=(
            "Suspects must be informed of their rights before custodial interrogation. "
            "Established the Miranda warning requirement."
        ),
        full_text=(
            "Ernesto Miranda confessed to crimes during police interrogation without being "
            "informed of his right to an attorney or right against self-incrimination. The "
            "Supreme Court held that the Fifth Amendment requires law enforcement to advise "
            "suspects of their rights before custodial questioning."
        ),
        tags=["criminal", "constitutional", "fifth amendment", "interrogation", "rights"],
        outcome="Confession inadmissible; Miranda warnings required",
    ),
    Precedent(
        case_name="Entick v Carrington",
        jurisdiction="England",
        year=1765,
        summary=(
            "Government officials cannot enter or search private property without lawful "
            "authority. Foundational case for property rights and civil liberties."
        ),
        full_text=(
            "King's messengers broke into John Entick's home and seized his papers under "
            "a general warrant. The court held the warrant was unlawful and that executive "
            "power does not extend to entering and searching private property without "
            "specific legal authority."
        ),
        tags=["property", "civil liberties", "search and seizure", "constitutional"],
        outcome="Unlawful search; general warrants invalid",
    ),
]

SAMPLE_LAWS: list[Law] = [
    Law(
        code="UCC",
        article="Article 2 - Sales",
        text=(
            "Uniform Commercial Code Article 2 governs the sale of goods. It establishes "
            "rules for contract formation, warranties, performance, breach, and remedies "
            "in transactions involving movable goods."
        ),
        jurisdiction="United States",
    ),
    Law(
        code="BGB",
        article="Section 823 - Tortious Liability",
        text=(
            "A person who intentionally or negligently unlawfully injures the life, body, "
            "health, freedom, property, or another right of another person is obligated to "
            "compensate the other person for the resulting damage."
        ),
        jurisdiction="Germany",
    ),
    Law(
        code="Civil Code",
        article="Article 1382 - Tort Liability",
        text=(
            "Any act of man which causes damage to another obliges the person by whose "
            "fault it occurred to repair it. General principle of fault-based liability "
            "in French civil law."
        ),
        jurisdiction="France",
    ),
    Law(
        code="Consumer Rights Act 2015",
        article="Section 9 - Satisfactory Quality",
        text=(
            "Every contract to supply goods is treated as including a term that the quality "
            "of the goods is satisfactory. Satisfactory quality considers fitness for "
            "purpose, appearance, freedom from minor defects, safety, and durability."
        ),
        jurisdiction="United Kingdom",
    ),
    Law(
        code="Sale of Goods Act 1979",
        article="Section 14 - Implied Terms about Quality",
        text=(
            "Where the seller sells goods in the course of a business, there is an implied "
            "term that the goods supplied are of satisfactory quality. Goods are of "
            "satisfactory quality if they meet the standard that a reasonable person would "
            "regard as satisfactory."
        ),
        jurisdiction="United Kingdom",
    ),
    Law(
        code="Restatement (Second) of Contracts",
        article="Section 90 - Promissory Estoppel",
        text=(
            "A promise which the promisor should reasonably expect to induce action or "
            "forbearance on the part of the promisee and which does induce such action "
            "or forbearance is binding if injustice can be avoided only by enforcement "
            "of the promise."
        ),
        jurisdiction="United States",
    ),
    Law(
        code="Employment Rights Act 1996",
        article="Section 94 - Right Not to be Unfairly Dismissed",
        text=(
            "An employee has the right not to be unfairly dismissed by his employer. An "
            "employer must show a fair reason for dismissal and that it acted reasonably "
            "in treating that reason as sufficient for dismissal."
        ),
        jurisdiction="United Kingdom",
    ),
    Law(
        code="Restatement (Second) of Torts",
        article="Section 402A - Strict Product Liability",
        text=(
            "One who sells any product in a defective condition unreasonably dangerous to "
            "the user or consumer is subject to liability for physical harm caused to the "
            "ultimate user or consumer. This applies even if the seller has exercised all "
            "possible care."
        ),
        jurisdiction="United States",
    ),
    Law(
        code="GDPR",
        article="Article 82 - Right to Compensation",
        text=(
            "Any person who has suffered material or non-material damage as a result of "
            "an infringement of the GDPR shall have the right to receive compensation "
            "from the controller or processor for the damage suffered."
        ),
        jurisdiction="European Union",
    ),
    Law(
        code="Limitation Act 1980",
        article="Section 2 - Time Limit for Tort Actions",
        text=(
            "An action founded on tort shall not be brought after the expiration of six "
            "years from the date on which the cause of action accrued."
        ),
        jurisdiction="United Kingdom",
    ),
]


def seed_database(db_path: Path | str = "data/legal_ref.db") -> LegalStore:
    """Seed the legal reference database with sample data.

    Returns the LegalStore instance with data loaded.
    """
    store = LegalStore(db_path=db_path)
    for precedent in SAMPLE_PRECEDENTS:
        store.insert_precedent(precedent)
    for law in SAMPLE_LAWS:
        store.insert_law(law)
    return store


if __name__ == "__main__":
    store = seed_database()
    conn = store._get_conn()
    p_count: int = conn.execute("SELECT COUNT(*) FROM precedents").fetchone()[0]
    l_count: int = conn.execute("SELECT COUNT(*) FROM laws").fetchone()[0]
    print(f"Seeded database with {p_count} precedents and {l_count} laws")
    store.close()
