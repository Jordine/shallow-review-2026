# Tagging example

One complete request from `src/tag_papers.py`, for the paper **Debate Training Reduces Reward Hacking in RLAIF** ([arXiv 2608.17776v1](https://arxiv.org/abs/2608.17776v1)).
A snapshot: it won't update when `facets.yaml` or the prompt changes.

Every paper gets the same system prompt and schema. Only the user message changes.

| | |
|---|---|
| Model | `claude-sonnet-5-5` |
| Effort | `medium` |
| Facets version | 2 |
| System prompt | 236 lines, 23,590 characters (cached across papers) |

## 1. System prompt

Built by `build_system_prompt()` from `facets.yaml` and the 2025 agendas (`input/taxonomy-2025.yaml`).

````markdown
You are an expert in technical AI alignment research tagging papers for the 2026 Shallow Review of AI safety, a reader's map of the field published on LessWrong.

For each paper you receive, assign tags along every facet below. Use only tags from the lists. Tag what the paper actually does, based on its title and abstract; do not tag a concept just because it is mentioned in passing. Fewer, accurate tags are better than many loose ones. Multi-tag facets may be empty when nothing fits.

## Evidence (evidence): exactly one tag

The strongest kind of support the paper offers for its main claim.

- proven: Formal proof or mathematical derivation.
- tested: Controlled experiment or intervention with a comparison (ablation, baseline, held-out test).
- measured: Systematic measurement or benchmark of existing systems, without an intervention.
- observed: Reports instances or case studies of behaviour, without systematic measurement.
- argued: Conceptual argument, position or framework, without new data.
- surveyed: Literature review or synthesis of other work.

## Scientific (contribution): one primary tag (the paper's main contribution) plus any secondary tags

What kind of scientific contribution the paper makes.

- notable phenomenon: Reports a new or surprising model behaviour.
- explanation: Explains why or how a known behaviour arises (mechanism, cause).
- measurement: Quantifies how often, how much or how well something happens.
- new method: Introduces a new technique for training, steering, monitoring, attacking or defending.
- benchmark: Releases a benchmark, dataset, environment or eval suite.
- tool: Releases software or infrastructure others can use.
- theory: Formal model, definitions or theorems.
- critique: Shows that a method, benchmark or claim is flawed or weaker than believed.
- replication: Reproduces or stress-tests prior results.
- negative result: Reports that something expected to work does not.
- position: Argues for a research direction, agenda or policy.
- synthesis: Organises existing work into a framework or survey.

## Paper type (paper_type): exactly one tag

The form of the paper.

- empirical study: Experiments on models to answer a research question.
- method paper: Proposes and evaluates a technique.
- benchmark paper: Mainly about a benchmark, dataset or environment.
- theory paper: Mainly formal or mathematical.
- position paper: Mainly argument or agenda.
- survey: Review of a field.
- incident report: Analysis of a real-world deployment incident or system card finding.
- technical report: Lab or institute report on a model, framework or evaluation programme.

## Concept (concept): any number of tags

The safety-relevant behaviours, risks and properties the paper is about (pick all that are central, usually 1-4).

- reward hacking: Exploiting flaws in rewards, graders or tests.
- specification gaming: Satisfying the letter but not the intent of an objective.
- deception: Models producing beliefs they know to be false.
- scheming: Covert pursuit of misaligned goals, alignment faking.
- sandbagging: Strategic underperformance.
- evaluation awareness: Models recognising tests and behaving differently.
- situational awareness: Models' knowledge of themselves and their circumstances.
- sycophancy: Telling users what they want to hear.
- emergent misalignment: Broad misalignment arising from narrow training.
- persona: Model character, identity, persona drift.
- introspection: Models reporting on their own internal states.
- model welfare: Moral status and wellbeing of models.
- cot faithfulness: Whether reasoning traces reflect the real computation.
- cot monitorability: Whether reasoning can be used to catch misbehaviour.
- steganography: Hidden information in model outputs.
- latent reasoning: Reasoning that is not verbalised.
- power seeking: Acquiring resources, influence or self-preservation.
- self-exfiltration: Escaping control, self-replication, weight theft by the model.
- sabotage: Deliberately undermining tasks or safety work.
- collusion: Coordination between AI systems against oversight.
- jailbreaks: Inputs that bypass safety training.
- prompt injection: Instructions smuggled in through tool outputs or documents.
- backdoors: Hidden triggers implanted in training data or weights.
- data poisoning: Corrupting training data.
- misuse: Harmful use by people (cyber, bio, persuasion, fraud).
- dangerous capabilities: Capabilities that could cause severe harm.
- honesty: Truthfulness, calibration, admitting uncertainty.
- refusals: When and how models decline requests.
- value alignment: Which values models hold and how they trade off.
- goal misgeneralization: Learning the wrong goal that fits training.
- corrigibility: Accepting correction and shutdown.
- oversight: Humans or AIs supervising more capable AIs.
- control: Safety measures that hold even if the model is misaligned.
- unlearning: Removing knowledge or capabilities from models.
- robustness: Reliability under distribution shift or attack.
- multi-agent risk: Risks arising from many interacting AI systems.
- societal impact: Effects on people, institutions, economy or power.
- governance: Policy, standards, regulation, safety frameworks.

## Method (method): any number of tags

The main research methods used (pick all that are central, usually 1-3).

- behavioural evals: Measuring behaviour from inputs and outputs.
- red teaming: Adversarially searching for failures.
- agentic environments: Running models as agents in sandboxes or simulated environments.
- model organisms: Deliberately training a model to have a property in order to study it.
- fine-tuning: Supervised fine-tuning as an experimental lever.
- rl training: Reinforcement learning as an experimental lever.
- pretraining data: Changing or studying pretraining data.
- probing: Linear or other probes on activations.
- sparse autoencoders: SAEs, transcoders and related dictionary methods.
- circuit analysis: Attribution graphs, circuits, causal interventions on components.
- steering: Activation steering or representation engineering.
- weight analysis: Studying or editing weights directly, model diffing.
- llm monitors: Using a model to monitor another model.
- cot analysis: Reading or intervening on chains of thought.
- formal methods: Proofs, verification, formal models.
- game theory: Game-theoretic or economic modelling.
- human studies: Experiments with human participants.
- scaling analysis: Trends across model size, compute or time.
- literature analysis: Reviewing or classifying existing work.

## Substrate (substrate): any number of tags

What kind of system the work is done on.

- frontier closed: Frontier proprietary models via API (GPT, Claude, Gemini, Grok).
- frontier internal: Internal or unreleased frontier models, lab-only access.
- open weights large: Open-weight models of roughly 30B parameters or more.
- open weights small: Open-weight models under roughly 30B parameters.
- toy models: Small purpose-built or synthetic models.
- agents: Models wrapped in agent scaffolds with tools.
- multimodal: Vision, audio or video models.
- no system: Theory, argument or policy with no experiments on models.

## About (developer) (developer): any number of tags

Whose models are studied or discussed, if specific developers' models are central to the paper.

- OpenAI: GPT and o-series models.
- Anthropic: Claude models.
- Google DeepMind: Gemini and Gemma models.
- Meta: Llama models.
- xAI: Grok models.
- DeepSeek: DeepSeek models.
- Alibaba: Qwen models.
- Mistral: Mistral models.

## 2025 agenda (agenda_2025): usually one, at most two

The research agendas from last year's Shallow Review. Pick the agenda(s) this paper most directly advances. If none is a reasonable fit, leave the list empty and name the new agenda in new_agenda (2-5 words, general enough that other papers could share it, e.g. 'persona science').

### Black-box safety (understand and control current model behaviour)

- Iterative alignment at pretrain-time: Guide weights during pretraining.
- Iterative alignment at post-train-time: Modify weights after pre-training.
- Black-box make-AI-solve-it: Focus on using existing models to improve and align further models.
- Inoculation prompting: Prompt mild misbehaviour in training, to prevent the failure mode where once AI misbehaves in a mild way, it will be more inclined towards all bad behaviour.
- Inference-time: In-context learning: Investigate what runtime guidelines, rules, or examples provided to an LLM yield better behavior.
- Inference-time: Steering: Manipulate an LLM's internal representations/token probabilities without touching weights.
- Capability removal: unlearning: Developing methods to selectively remove specific information, capabilities, or behaviors from a trained model (e.g. without retraining it from scratch). A mixture of black-box and white-box approaches.
- Control: If we assume early transformative AIs are misaligned and actively trying to subvert safety measures, can we still set up protocols to extract useful work from them while preventing sabotage, and watching with incriminating behaviour?
- Safeguards (inference-time auxiliaries): Layers of inference-time defenses, such as classifiers, monitors, and rapid-response protocols, to detect and block jailbreaks, prompt injections, and other harmful model behaviors.
- Chain of thought monitoring: Supervise an AI's natural-language (output) "reasoning" to detect misalignment, scheming, or deception, rather than studying the actual internal states.
- Model values / model preferences: Analyse and control emergent, coherent value systems in LLMs, which change as models scale, and can contain problematic values like preferences for AIs over humans.
- Character training and persona steering: Map, shape, and control the personae of language models, such that new models embody desirable values (e.g., honesty, empathy) rather than undesirable ones (e.g., sycophancy, self-perpetuating behaviors).
- Emergent misalignment: Fine-tuning LLMs on one narrow antisocial task can cause general misalignment including deception, shutdown resistance, harmful advice, and extremist sympathies, when those behaviors are never trained or rewarded directly. [A new agenda](https://www.lesswrong.com/posts/AcTEiu5wYDgrbmXow/open-problems-in-emergent-misalignment) which quickly led to a stream of exciting work.
- Model specs and constitutions: Write detailed, natural language descriptions of values and rules for models to follow, then instill these values and rules into models via techniques like Constitutional AI or deliberative alignment.
- Model psychopathology: Find interesting LLM phenomena like glitch [tokens](https://vgel.me/posts/seahorse/) and the reversal curse; these are vital data for theory.
- Data filtering: Builds safety into models from the start by removing harmful or toxic content (like dual-use info) from the pretraining data, rather than relying only on post-training alignment.
- Hyperstition studies: Study, steer, and intervene on the following feedback loop: "we produce stories about how present and future AI systems behave" → "these stories become training data for the AI" → "these stories shape how AI systems in fact behave".
- Data poisoning defense: Develops methods to detect and prevent malicious or backdoor-inducing samples from being included in the training data.
- Synthetic data for alignment: Uses AI-generated data (e.g., critiques, preferences, or self-labeled examples) to scale and improve alignment, especially for superhuman models.
- Data quality for alignment: Improves the quality, signal-to-noise ratio, and reliability of human-generated preference and alignment data.
- Mild optimisation: Avoid Goodharting by getting AI to satisfice rather than maximise.
- RL safety: Improves the robustness of reinforcement learning agents by addressing core problems in reward learning, goal misgeneralization, and specification gaming.
- Assistance games, assistive agents: Formalize how AI assistants learn about human preferences given uncertainty and partial observability, and construct environments which better incentivize AIs to learn what we want them to learn.
- Harm reduction for open weights: Develops methods, primarily based on pretraining data intervention, to create tamper-resistant safeguards that prevent open-weight models from being maliciously fine-tuned to remove safety features or exploit dangerous capabilities.
- The "Neglected Approaches" Approach: Agenda-agnostic approaches to identifying good but overlooked empirical alignment ideas, working with theorists who could use engineers, and prototyping them.

### White-box safety (i.e. Interpretability)

- Reverse engineering: Decompose a model into its functional, interacting components (circuits), formally describe what computation those components perform, and validate their causal effects to reverse-engineer the model's internal algorithm.
- Extracting latent knowledge: Identify and decoding the "true" beliefs or knowledge represented inside a model's activations, even when the model's output is deceptive or false.
- Lie and deception detectors: Detect when a model is being deceptive or lying by building white- or black-box detectors. Some work below requires intent in their definition, while other work focuses only on whether the model states something it believes to be false, regardless of intent.
- Model diffing: Understand what happens when a model is finetuned, what the "diff" between the finetuned and the original model consists in.
- Sparse Coding: Decompose the polysemantic activations of the residual stream into a sparse linear combination of monosemantic "features" which correspond to interpretable concepts.
- Causal Abstractions: Verify that a neural network implements a specific high-level causal model (like a logical algorithm) by finding a mapping between high-level variables and low-level neural representations.
- Data attribution: Quantifies the influence of individual training data points on a model's specific behavior or output, allowing researchers to trace model properties (like misalignment, bias, or factual errors) back to their source in the training set.
- Pragmatic interpretability: Directly tackling concrete, safety-critical problems on the path to AGI by using lightweight interpretability tools (like steering and probing) and empirical feedback from proxy tasks, rather than pursuing complete mechanistic reverse-engineering.
- Other interpretability: Interpretability that does not fall well into other categories.
- Learning dynamics and developmental interpretability: Builds tools for detecting, locating, and interpreting key structural shifts, phase transitions, and emergent phenomena (like grokking or deception) that occur during a model's training and in-context learning phases.
- Representation structure and geometry: What do the representations look like? Does any simple structure underlie the beliefs of all well-trained models? Can we get the semantics from this geometry?
- Human inductive biases: Discover connections deep learning AI systems have with human brains and human learning processes. Develop an 'alignment moonshot' based on a coherent theory of learning which applies to both humans and AI systems.
- Monitoring concepts: Identifies directions or subspaces in a model's latent state that correspond to high-level concepts (like refusal, deception, or planning) and uses them to audit models for misalignment, monitor them at runtime, suppress eval awareness, debug why models are failing, etc.
- Activation engineering: Programmatically modify internal model activations to steer outputs toward desired behaviors; a lightweight, interpretable supplement to fine-tuning.

### Safety by construction

- Guaranteed-Safe AI: Have an AI system generate outputs (e.g. code, control systems, or RL policies) which it can quantitatively guarantee comply with a formal safety specification and world model.
- Scientist AI: Develop powerful, nonagentic, uncertain world models that accelerate scientific progress while avoiding the risks of agent AIs
- Brainlike-AGI Safety: Social and moral instincts are (partly) implemented in particular hardwired brain circuitry; let's figure out what those circuits are and how they work; this will involve symbol grounding. "a yet-to-be-invented variation on actor-critic model-based reinforcement learning"

### Make AI solve it

- Weak-to-strong generalization: Use weaker models to supervise and provide a feedback signal to stronger models.
- Supervising AIs improving AIs: Build formal and empirical frameworks where AIs supervise other (stronger) AI systems via structured interactions; construct monitoring tools which enable scalable tracking of behavioural drift, benchmarks for self-modification, and robustness guarantees
- AI explanations of AIs: Make open AI tools to explain AIs, including AI agents. e.g. automatic feature descriptions for neuron activation patterns; an interface for steering these features; a behaviour elicitation agent that "searches" for a specified behaviour in frontier models.
- Debate: In the limit, it's easier to compellingly argue for true claims than for false claims; exploit this asymmetry to get trusted work out of untrusted debaters.
- LLM introspection training: Train LLMs to the predict the outputs of high-quality whitebox methods, to induce general self-explanation skills that use its own 'introspective' access

### Theory

- Agent foundations: Develop philosophical clarity and mathematical formalizations of building blocks that might be useful for plans to align strong superintelligence, such as agency, optimization strength, decision theory, abstractions, concepts, etc.
- Tiling agents: An aligned agentic system modifying itself into an unaligned system would be bad and we can research ways that this could occur and infrastructure/approaches that prevent it from happening.
- High-Actuation Spaces: Mech interp and alignment assume a stable "computational substrate" (linear algebra on GPUs). If later AI uses different substrates (e.g. something neuromorphic), methods like probes and steering will not transfer. Therefore, better to try and infer goals via a "telic DAG" which abstracts over substrates, and so sidestep the issue of how to define intermediate representations. Category theory is intended to provide guarantees that this abstraction is valid.
- Asymptotic guarantees: Prove that if a safety process has enough resources (human data quality, training time, neural network capacity), then in the limit some system specification will be guaranteed. Use complexity theory, game theory, learning theory and other areas to both improve asymptotic guarantees and develop ways of showing convergence.
- Heuristic explanations: Formalize mechanistic explanations of neural network behavior, automate the discovery of these "heuristic explanations" and use them to predict when novel input will lead to extreme behavior (i.e. "Low Probability Estimation" and "Mechanistic Anomaly Detection").
- Behavior alignment theory: Predict properties of future AGI (e.g. power-seeking) with formal models; formally state and prove hypotheses about the properties powerful systems will have and how we might try to change them.
- Other corrigibility: Diagnose and communicate obstacles to achieving robustly corrigible behavior; suggest mechanisms, tests, and escalation channels for surfacing and mitigating incorrigible behaviors
- Natural abstractions: *Develop a theory of concepts that explains how they are learned, how they structure a particular system's understanding, and how mutual translatability can be achieved between different collections of concepts.*
- The Learning-Theoretic Agenda: Create a mathematical theory of intelligent agents that encompasses both humans and the AIs we want, one that specifies what it means for two such agents to be aligned; translate between its ontology and ours; produce formal desiderata for a training setup that produces coherent AGIs similar to (our model of) an aligned agent

### Multi-agent first

- Aligning to context: Align AI directly to the role of participant, collaborator, or advisor for our best real human practices and institutions, instead of aligning AI to separately representable goals, rules, or utility functions.
- Aligning to the social contract: Generate AIs' operational values from 'social contract'-style ideal civic deliberation formalisms and their consequent rulesets for civic actors
- Theory for aligning multiple AIs: Use realistic game-theory variants (e.g. evolutionary game theory, computational game theory) or develop alternative game theories to describe/predict the collective and individual behaviours of AI agents in multi-agent scenarios.
- Tools for aligning multiple AIs: Develop tools and techniques for designing and testing multi-agent AI scenarios, for auditing real-world multi-agent AI dynamics, and for aligning AIs in multi-AI settings.
- Aligned to who?: Technical protocols for taking seriously the plurality of human values, cultures, and communities when aligning AI to "humanity"
- Aligning what?: Develop alternatives to agent-level models of alignment, by treating human-AI interactions, AI-assisted institutions, AI economic or cultural systems, drives within one AI, and other causal/constitutive processes as subject to alignment

### Evals

- AGI metrics: Evals with the explicit aim of measuring progress towards full human-level generality.
- Capability evals: Make tools that can actually check whether a model has a certain capability or propensity. We default to low-n sampling of a vast latent space but aim to do better.
- Autonomy evals: Measure an AI's ability to act autonomously to complete long-horizon, complex tasks.
- WMD evals (Weapons of Mass Destruction): Evaluate whether AI models possess dangerous knowledge or capabilities related to biological and chemical weapons, such as biosecurity or chemical synthesis.
- Situational awareness and self-awareness evals: Evaluate if models understand their own internal states and behaviors, their environment, and whether they are in a test or real-world deployment.
- Steganography evals: Evaluate whether models can hide secret information or encoded reasoning in their outputs, such as in chain-of-thought scratchpads, to evade monitoring.
- AI deception evals: research demonstrating that AI models, particularly agentic ones, can learn and execute deceptive behaviors such as alignment faking, manipulation, and sandbagging.
- AI scheming evals: Evaluate frontier models for scheming, a sophisticated, strategic form of AI deception where a model covertly pursues a misaligned, long-term objective while deliberately faking alignment and compliance to evade detection by human supervisors and safety mechanisms.
- Sandbagging evals: Evaluate whether AI models deliberately hide their true capabilities or underperform, especially when they detect they are in an evaluation context.
- Self-replication evals: evaluate whether AI agents can autonomously replicate themselves by obtaining their own weights, securing compute resources, and creating copies of themselves.
- Various Redteams: attack current models and see what they do / deliberately induce bad things on current frontier models to test out our theories / methods.
- Other evals: A collection of miscellaneous evaluations for specific alignment properties, such as honesty, shutdown resistance and sycophancy.
````

## 2. User message

Built by `user_message()` from the paper's row in `input/arxiv-papers-shortlisted.csv`.

````text
Tag this paper.

Title: Debate Training Reduces Reward Hacking in RLAIF
Authors: Zachary Kenton, Lili Janzer, Rory Greig, Tian Huey Teh, Kirill Tyshchuk, Jonah Brown-Cohen, Harri Edwards, Senthooran Rajamanoharan, Noah Y. Siegel, Natasha Jaques, Rohin Shah
Published: 2026-08-18
arXiv categories: cs.LG
Comment: none
Venue: none

Abstract:
We demonstrate that RL finetuning an LLM using debate, a two-player adversarial game between a generator and a critic adjudicated by a weaker LLM judge, reduces reward hacking compared to a reinforcement learning from AI feedback (RLAIF) baseline. Reward hacking is a central obstacle in RLAIF: as training progresses, the policy learns to exploit systematic errors in its AI judge, degrading task performance, a problem that worsens precisely when the judge is weaker than the policy, the setting most relevant to overseeing increasingly capable AI systems. We study mathematics tasks, where final-answer correctness is verifiable, allowing us to measure reward hacking dynamics. We train a Gemini~2.5 Flash-class policy with a frozen, weaker Gemini~2.5 Flash Lite judge, comparing a single-player RLAIF baseline against debate. While the baseline quickly hacks the judge, debate maintains judge performance throughout training, leading to a higher peak validation accuracy (45\% performance gap recovered) that persists through many RL steps. Additional experiments show that: 1) further weakening the judge leads to faster hacking, but this can be compensated by adding an additional debate round; 2) debate incentives override prompted misalignment; 3) RL using an LLM judge has a smaller train/validation reward gap than RL from verifiable rewards; 4) learning to critique to convince the judge using ground truth labels is possible but slow. Taken together, our results are a positive update on the feasibility of debate, while highlighting that balancing multi-agent training is critical: without player constraints, adversarial training risks defaulting to critic judge-hacking. We show that critique word limits (effective up to 150 words) successfully balance the game and avoid judge hacking, though this introduces a trade-off by restricting critic expressive clarity.
````

## 3. Output schema

Built by `build_schema()`. The API holds Claude's answer to this JSON schema, so every tag must come from its
facet's `enum` list. Single-choice facets are strings; multi-choice facets are arrays, which may be empty.

````json
{
  "properties": {
    "summary": {
      "description": "One or two plain sentences on what the paper does and finds.",
      "title": "Summary",
      "type": "string"
    },
    "evidence": {
      "enum": [
        "proven",
        "tested",
        "measured",
        "observed",
        "argued",
        "surveyed"
      ],
      "title": "Evidence",
      "type": "string"
    },
    "contribution_primary": {
      "enum": [
        "notable phenomenon",
        "explanation",
        "measurement",
        "new method",
        "benchmark",
        "tool",
        "theory",
        "critique",
        "replication",
        "negative result",
        "position",
        "synthesis"
      ],
      "title": "Contribution Primary",
      "type": "string"
    },
    "contribution_secondary": {
      "items": {
        "enum": [
          "notable phenomenon",
          "explanation",
          "measurement",
          "new method",
          "benchmark",
          "tool",
          "theory",
          "critique",
          "replication",
          "negative result",
          "position",
          "synthesis"
        ],
        "type": "string"
      },
      "title": "Contribution Secondary",
      "type": "array"
    },
    "paper_type": {
      "enum": [
        "empirical study",
        "method paper",
        "benchmark paper",
        "theory paper",
        "position paper",
        "survey",
        "incident report",
        "technical report"
      ],
      "title": "Paper Type",
      "type": "string"
    },
    "concept": {
      "items": {
        "enum": [
          "reward hacking",
          "specification gaming",
          "deception",
          "scheming",
          "sandbagging",
          "evaluation awareness",
          "situational awareness",
          "sycophancy",
          "emergent misalignment",
          "persona",
          "introspection",
          "model welfare",
          "cot faithfulness",
          "cot monitorability",
          "steganography",
          "latent reasoning",
          "power seeking",
          "self-exfiltration",
          "sabotage",
          "collusion",
          "jailbreaks",
          "prompt injection",
          "backdoors",
          "data poisoning",
          "misuse",
          "dangerous capabilities",
          "honesty",
          "refusals",
          "value alignment",
          "goal misgeneralization",
          "corrigibility",
          "oversight",
          "control",
          "unlearning",
          "robustness",
          "multi-agent risk",
          "societal impact",
          "governance"
        ],
        "type": "string"
      },
      "title": "Concept",
      "type": "array"
    },
    "method": {
      "items": {
        "enum": [
          "behavioural evals",
          "red teaming",
          "agentic environments",
          "model organisms",
          "fine-tuning",
          "rl training",
          "pretraining data",
          "probing",
          "sparse autoencoders",
          "circuit analysis",
          "steering",
          "weight analysis",
          "llm monitors",
          "cot analysis",
          "formal methods",
          "game theory",
          "human studies",
          "scaling analysis",
          "literature analysis"
        ],
        "type": "string"
      },
      "title": "Method",
      "type": "array"
    },
    "substrate": {
      "items": {
        "enum": [
          "frontier closed",
          "frontier internal",
          "open weights large",
          "open weights small",
          "toy models",
          "agents",
          "multimodal",
          "no system"
        ],
        "type": "string"
      },
      "title": "Substrate",
      "type": "array"
    },
    "developer": {
      "items": {
        "enum": [
          "OpenAI",
          "Anthropic",
          "Google DeepMind",
          "Meta",
          "xAI",
          "DeepSeek",
          "Alibaba",
          "Mistral"
        ],
        "type": "string"
      },
      "title": "Developer",
      "type": "array"
    },
    "agenda_2025": {
      "items": {
        "enum": [
          "Iterative alignment at pretrain-time",
          "Iterative alignment at post-train-time",
          "Black-box make-AI-solve-it",
          "Inoculation prompting",
          "Inference-time: In-context learning",
          "Inference-time: Steering",
          "Capability removal: unlearning",
          "Control",
          "Safeguards (inference-time auxiliaries)",
          "Chain of thought monitoring",
          "Model values / model preferences",
          "Character training and persona steering",
          "Emergent misalignment",
          "Model specs and constitutions",
          "Model psychopathology",
          "Data filtering",
          "Hyperstition studies",
          "Data poisoning defense",
          "Synthetic data for alignment",
          "Data quality for alignment",
          "Mild optimisation",
          "RL safety",
          "Assistance games, assistive agents",
          "Harm reduction for open weights",
          "The \"Neglected Approaches\" Approach",
          "Reverse engineering",
          "Extracting latent knowledge",
          "Lie and deception detectors",
          "Model diffing",
          "Sparse Coding",
          "Causal Abstractions",
          "Data attribution",
          "Pragmatic interpretability",
          "Other interpretability",
          "Learning dynamics and developmental interpretability",
          "Representation structure and geometry",
          "Human inductive biases",
          "Monitoring concepts",
          "Activation engineering",
          "Guaranteed-Safe AI",
          "Scientist AI",
          "Brainlike-AGI Safety",
          "Weak-to-strong generalization",
          "Supervising AIs improving AIs",
          "AI explanations of AIs",
          "Debate",
          "LLM introspection training",
          "Agent foundations",
          "Tiling agents",
          "High-Actuation Spaces",
          "Asymptotic guarantees",
          "Heuristic explanations",
          "Behavior alignment theory",
          "Other corrigibility",
          "Natural abstractions",
          "The Learning-Theoretic Agenda",
          "Aligning to context",
          "Aligning to the social contract",
          "Theory for aligning multiple AIs",
          "Tools for aligning multiple AIs",
          "Aligned to who?",
          "Aligning what?",
          "AGI metrics",
          "Capability evals",
          "Autonomy evals",
          "WMD evals (Weapons of Mass Destruction)",
          "Situational awareness and self-awareness evals",
          "Steganography evals",
          "AI deception evals",
          "AI scheming evals",
          "Sandbagging evals",
          "Self-replication evals",
          "Various Redteams",
          "Other evals"
        ],
        "type": "string"
      },
      "title": "Agenda 2025",
      "type": "array"
    },
    "new_agenda": {
      "description": "Empty unless no 2025 agenda fits; then a short name for the new agenda.",
      "title": "New Agenda",
      "type": "string"
    }
  },
  "required": [
    "summary",
    "evidence",
    "contribution_primary",
    "contribution_secondary",
    "paper_type",
    "concept",
    "method",
    "substrate",
    "developer",
    "agenda_2025",
    "new_agenda"
  ],
  "title": "PaperTags",
  "type": "object"
}
````

## 4. Claude's structured output

What Claude returned for this paper, as saved in `output/tags.jsonl` (`arxiv_id`, `model` and `facets_version` are
added by the script).

````json
{
  "arxiv_id": "2608.17776v1",
  "model": "claude-sonnet-5-5",
  "facets_version": 2,
  "summary": "Shows that RL finetuning a Gemini 2.5 Flash-class policy via debate (generator vs critic, judged by a weaker Gemini Flash Lite) reduces reward hacking of the AI judge on math tasks compared to a single-player RLAIF baseline. Additional experiments cover judge weakness, extra debate rounds, prompted misalignment, and critic word limits to balance the game.",
  "evidence": "tested",
  "contribution_primary": "new method",
  "contribution_secondary": [
    "measurement",
    "negative result"
  ],
  "paper_type": "empirical study",
  "concept": [
    "reward hacking",
    "oversight"
  ],
  "method": [
    "rl training",
    "behavioural evals"
  ],
  "substrate": [
    "frontier closed"
  ],
  "developer": [
    "Google DeepMind"
  ],
  "agenda_2025": [
    "Debate"
  ],
  "new_agenda": ""
}
````
