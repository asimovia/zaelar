---
title: Principles
updated: 2026-09-15
status: stable
---

# The base of the whole system — mechanisms, not rules

The operator's own statement of it, 2026-09-15, verbatim and load-bearing:

> «Necesitamos un sistema que no esté educado, es decir, que sea inteligente y que sepa qué hacer. Yo no
> puedo decirte todo caso por caso. Eso sería un sistema de if-elses. Nosotros tenemos un sistema
> inteligente conectado a modelos de lenguaje que es capaz de entender las tareas, procesarlas y de tomar
> sus propias decisiones. Solo necesitamos darle no solo esa libertad, sino esos mecanismos que sean
> capaces de entender, ejecutar y comprobar, que nos permitan que cualquier tipo de tarea sea plausible y
> realizable por parte de nuestro agente. […] Si no tiene algo claro le tendrá que preguntar al usuario, y
> si el usuario no está tendrá que tomar una decisión, y con lo que le diga al usuario tendrá que montar
> unas reglas dinámicas que se irán adaptando a cada operador. Al final estamos creando un SISTEMA, no una
> banda de reglas predefinidas o de carriles preseteados. Lo único que tiene carriles son los widgets.»

This is not a preference about style. It is the criterion that decides whether a change belongs in this
engine at all, and it outranks the convenience of any individual fix.

## The line that actually works

«No rules» is not the rule — the destructive-action contract (V2-705) is a rule, and it is the one that
stopped 147 DELETE requests against his real calendar. The distinction that survives contact with the code
is **what the rule is about**:

| | Rail on CONSEQUENCES — a MECHANISM, keep it | Rail on JUDGEMENT — a LIMIT, remove it |
|---|---|---|
| What it constrains | what may irreversibly happen; what a door accepts; what a mandate allows | what to say, when something counts as X, how to behave |
| Effect on the model | none — it reasons freely and the engine bounds the outcome | it stops reasoning and follows the script |
| Examples here | `party.py` offers **no tools** at all; `contract.guard` refuses a destructive action with an empty selector; `book.unbook` can only unwrite the row that errand wrote; a mandate's `may` list | «no discutas»; «acúsale recibo en una frase»; «si te pide X responde Y»; a verb table that decides intent |

`nucleo/errands/party.py` is the template and should be read before designing anything in this class: the
highest-consequence mouth in the engine writes to real people on the operator's real accounts, and it is
made safe **structurally** — the model returns ONE JSON object and the ENGINE executes what the mandate
allows, so a stranger's sentence cannot reach a tool because no tool is offered. Freedom of reasoning,
zero freedom of consequence. Every rail worth having has that shape.

## The three duties this puts on any change

1. **Declare capabilities, never script behaviour.** An undeclared capability is one the model narrates
   instead of using (V2-540); a capability it is told it lacks is one it talks the operator out of
   (V2-692). So say what it MAY do, once — and stop there. *Measured 2026-09-15: a paragraph added the same
   night told the party model «no discutas», «acúsale recibo en una frase» and where to put what the person
   said. Three rails on judgement, smuggled in as help, in a fix that was otherwise a mechanism.*
2. **When it is not clear: ask. When nobody answers: decide, and remember what was decided.** `ask_operator`
   is the asking half. The remembering half — turning his answer into a durable policy that the NEXT
   decision of the same class consults — is the part that makes the system adapt per operator instead of
   per release. See the gap below; until it exists, every preference he states either dies in a
   conversation or gets frozen into a prompt by whoever was working that day.
3. **Widgets are the only place rails belong.** A widget has a declared shape: its `manifest.json` actions
   ARE its skills, its `data.py` owns its data, its store is its state. System widgets ship that shape
   predetermined and the operator may change it. Nothing else in the engine gets to be a rail — not the
   router, not the prompts, not the playbooks.

## The known gap (open)

There is no **per-operator policy store**: no mechanism that takes an answer the operator gave to a
question the system asked, and makes it the default the same class of decision reads next time. Today the
engine can ask (`ask_operator`, the confirm gates) and can remember facts (`memory/`, pills), but the loop
between them is not closed, so preferences keep being converted into constants in prompts and code. This
is the single highest-value thing missing from the philosophy above, and it is why the same kind of
question keeps reaching him.

## Fix the class, never the case (CRIT-W10, 2026-10-19)

> «No más arreglos para que tests individuales funcionen. Tenemos que hacer mejoras a nivel estructural que
> arreglen el sistema y como resultado los tests funcionen. Esto es un producto global, que debe poder atender
> cualquier request.» — the operator, after the 72-hour audit V2-783 classified 30 of 99 product commits as a
> regex, a word table or a net over the model's words, each born from one recorded case.

The tests and the judge are a SAMPLE of the requests the product will meet. Green on the sample is the
consequence of a sound system, never the target. So:

1. **Name the class before touching code.** «The sheet rejects LG rows» is a case; «the sheet's subject is read
   from capital letters» is the class. If you cannot name the class, you have not found the cause yet.
2. **Reach for structure in this order:** a verdict the turn already pays (Jev, the brief) → a datum someone
   declares (a manifest action, the research brief, the connector catalogue) → one door / one reader that every
   route crosses → and only then language data, in `i18n/`, for every language at once.
3. **The test proves the class, not the case:** it carries at least one variant the failing case did not — the
   other language, a reworded request, another domain, an input shape nobody recorded.
4. **Forbidden, whatever the deadline:** a regex or word list added so one case passes; a case id or a fixture's
   string in product code; weakening or rewriting an assertion to go green (an assertion changes only when the
   behaviour changed on purpose, and the commit says so); raising any ratchet ceiling.
5. **When the structural fix does not fit the batch,** the test stays red (or `xfail` with the class as its
   reason) and the class goes into the initiative. An honest red beats a patched green: a patched green hides the
   class from the next person and from the judge.

Enforced, not just written: `tests/infrastructure/unit/test_words_never_fix_a_case.py` (node 7.73) — the count
of `re.compile` calls and module-level word tables in product code may only fall.

## How to tell you are violating this

Before writing the change, ask the two questions the Brain Worker doctrine already asks
(`.meshkore/docs/architecture/zaelar-brain-worker-doctrine.md`), then a third:

- Change one word of the request — hotel→restaurante, Sevilla→Los Ángeles — **does it still stand?**
- Does it work for a task nobody has written yet?
- **Is what I am adding a sentence about how to behave?** If yes, it is a rail on judgement. Delete it and
  find the mechanism it was standing in for.
- **Would this change exist if that one test did not?** If no, it is a patch for the test (CRIT-W10).
