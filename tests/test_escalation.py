"""Tests for judicial hierarchy model and escalation engine."""

import json
from pathlib import Path

import pytest

from backend.models.case import (
    Case,
    CaseStatus,
    CourtEvaluation,
    JudicialLevel,
)
from backend.models.hierarchy import (
    LEVEL_ORDER,
    EscalationCriteria,
    JudicialHierarchy,
    load_hierarchy,
)
from backend.services.case_folder import CaseFolderManager
from backend.services.escalation import (
    EscalationEngine,
    EscalationResult,
)

# --- Fixtures ---


@pytest.fixture
def hierarchy() -> JudicialHierarchy:
    """Load the default judicial hierarchy from config."""
    return load_hierarchy()


@pytest.fixture
def folder_manager(tmp_path: Path) -> CaseFolderManager:
    return CaseFolderManager(base_path=tmp_path)


@pytest.fixture
def sample_case() -> Case:
    return Case(
        id="test-case-001",
        title="Test Contract Dispute",
        facts="Party A claims breach of contract by Party B.",
    )


@pytest.fixture
def sample_evaluation() -> CourtEvaluation:
    return CourtEvaluation(
        consistency_scores={"claimant": 0.8, "respondent": 0.7},
        compliance_assessment={
            "claimant": "Compliant",
            "respondent": "Minor issues",
        },
        preliminary_opinion="The claimant has a stronger position.",
        adversarial_challenge="The respondent's evidence may be underweighted.",
        reconciled_decision="Claimant prevails on balance of evidence.",
        escalation_recommendation="no_escalation",
        reasoning_trace=["Analyzed claims", "Reviewed evidence", "Formed opinion"],
    )


@pytest.fixture
def escalation_evaluation() -> CourtEvaluation:
    """Evaluation with escalation recommendation."""
    return CourtEvaluation(
        consistency_scores={"claimant": 0.6, "respondent": 0.6},
        compliance_assessment={
            "claimant": "Compliant",
            "respondent": "Compliant",
        },
        preliminary_opinion="Both sides have merit.",
        adversarial_challenge="Constitutional question arises from contract clause.",
        reconciled_decision="Case involves constitutional question about contract freedom.",
        escalation_recommendation="escalate_constitutional",
        reasoning_trace=[
            "Analyzed claims",
            "Constitutional issue identified",
        ],
    )


# --- Hierarchy Model Tests ---


class TestJudicialHierarchy:
    def test_load_hierarchy_from_config(self, hierarchy: JudicialHierarchy) -> None:
        assert len(hierarchy.levels) == 4
        assert hierarchy.levels[0].id == "first_instance"
        assert hierarchy.levels[1].id == "appeals"
        assert hierarchy.levels[2].id == "superior"
        assert hierarchy.levels[3].id == "supreme"

    def test_level_names(self, hierarchy: JudicialHierarchy) -> None:
        names = [level.name for level in hierarchy.levels]
        assert names == [
            "First Instance",
            "Appeals Court",
            "Superior Court",
            "Supreme Court",
        ]

    def test_get_level_config(self, hierarchy: JudicialHierarchy) -> None:
        config = hierarchy.get_level_config(JudicialLevel.first_instance)
        assert config is not None
        assert config.name == "First Instance"
        assert len(config.procedural_requirements) > 0

    def test_get_level_config_all_levels(self, hierarchy: JudicialHierarchy) -> None:
        for level in JudicialLevel:
            config = hierarchy.get_level_config(level)
            assert config is not None, f"Missing config for {level}"

    def test_get_next_level(self, hierarchy: JudicialHierarchy) -> None:
        assert hierarchy.get_next_level(JudicialLevel.first_instance) == JudicialLevel.appeals
        assert hierarchy.get_next_level(JudicialLevel.appeals) == JudicialLevel.superior
        assert hierarchy.get_next_level(JudicialLevel.superior) == JudicialLevel.supreme
        assert hierarchy.get_next_level(JudicialLevel.supreme) is None

    def test_is_highest_level(self, hierarchy: JudicialHierarchy) -> None:
        assert not hierarchy.is_highest_level(JudicialLevel.first_instance)
        assert not hierarchy.is_highest_level(JudicialLevel.appeals)
        assert not hierarchy.is_highest_level(JudicialLevel.superior)
        assert hierarchy.is_highest_level(JudicialLevel.supreme)

    def test_level_order(self) -> None:
        assert LEVEL_ORDER == [
            JudicialLevel.first_instance,
            JudicialLevel.appeals,
            JudicialLevel.superior,
            JudicialLevel.supreme,
        ]

    def test_escalation_criteria_defaults(self) -> None:
        criteria = EscalationCriteria()
        assert not criteria.constitutional_questions
        assert not criteria.conflicting_precedents
        assert not criteria.procedural_irregularities
        assert criteria.explicit_recommendation

    def test_first_instance_escalation_criteria(
        self, hierarchy: JudicialHierarchy
    ) -> None:
        config = hierarchy.get_level_config(JudicialLevel.first_instance)
        assert config is not None
        # First instance doesn't allow constitutional or conflicting precedent escalation
        assert not config.escalation_criteria.constitutional_questions
        assert not config.escalation_criteria.conflicting_precedents

    def test_appeals_escalation_criteria(self, hierarchy: JudicialHierarchy) -> None:
        config = hierarchy.get_level_config(JudicialLevel.appeals)
        assert config is not None
        assert config.escalation_criteria.constitutional_questions
        assert config.escalation_criteria.conflicting_precedents

    def test_supreme_no_escalation_criteria(
        self, hierarchy: JudicialHierarchy
    ) -> None:
        config = hierarchy.get_level_config(JudicialLevel.supreme)
        assert config is not None
        # Supreme court has empty escalation criteria (nowhere to escalate)
        assert not config.escalation_criteria.constitutional_questions
        assert not config.escalation_criteria.conflicting_precedents

    def test_load_hierarchy_custom_path(self, tmp_path: Path) -> None:
        custom_config = {
            "levels": [
                {
                    "id": "first_instance",
                    "name": "Trial Court",
                    "jurisdiction_scope": "All matters",
                    "escalation_criteria": {},
                    "procedural_requirements": ["Review"],
                }
            ]
        }
        config_file = tmp_path / "custom_hierarchy.json"
        config_file.write_text(json.dumps(custom_config))
        hierarchy = load_hierarchy(config_file)
        assert len(hierarchy.levels) == 1
        assert hierarchy.levels[0].name == "Trial Court"


# --- Escalation Result Tests ---


class TestEscalationResult:
    def test_to_dict(self) -> None:
        result = EscalationResult(
            should_escalate=True,
            reason="Constitutional question",
            current_level=JudicialLevel.first_instance,
            next_level=JudicialLevel.appeals,
            triggers=["Constitutional question detected"],
        )
        d = result.to_dict()
        assert d["should_escalate"] is True
        assert d["current_level"] == "First Instance"
        assert d["next_level"] == "Appeals Court"
        assert len(d["triggers"]) == 1  # type: ignore[arg-type]

    def test_to_dict_no_escalation(self) -> None:
        result = EscalationResult(
            should_escalate=False,
            reason="No criteria met",
            current_level=JudicialLevel.first_instance,
        )
        d = result.to_dict()
        assert d["should_escalate"] is False
        assert d["next_level"] is None
        assert d["triggers"] == []


# --- Escalation Engine Tests ---


class TestEscalationEngine:
    def test_no_escalation_when_not_recommended(
        self, hierarchy: JudicialHierarchy, sample_evaluation: CourtEvaluation
    ) -> None:
        engine = EscalationEngine(hierarchy=hierarchy)
        result = engine.check_escalation(
            sample_evaluation, JudicialLevel.first_instance
        )
        assert not result.should_escalate
        assert result.reason == "No escalation criteria met"

    def test_no_escalation_at_highest_level(
        self, hierarchy: JudicialHierarchy, escalation_evaluation: CourtEvaluation
    ) -> None:
        engine = EscalationEngine(hierarchy=hierarchy)
        result = engine.check_escalation(escalation_evaluation, JudicialLevel.supreme)
        assert not result.should_escalate
        assert "highest judicial level" in result.reason

    def test_escalation_on_constitutional_from_appeals(
        self, hierarchy: JudicialHierarchy, escalation_evaluation: CourtEvaluation
    ) -> None:
        """Appeals court allows constitutional escalation."""
        engine = EscalationEngine(hierarchy=hierarchy)
        result = engine.check_escalation(
            escalation_evaluation, JudicialLevel.appeals
        )
        assert result.should_escalate
        assert result.next_level == JudicialLevel.superior

    def test_escalation_recommendation_triggers(
        self, hierarchy: JudicialHierarchy
    ) -> None:
        """Test that explicit recommendation alone triggers escalation."""
        evaluation = CourtEvaluation(
            escalation_recommendation="escalate_conflicting_precedents",
            reconciled_decision="Conflicting precedents found.",
            reasoning_trace=["Reviewed case law"],
        )
        engine = EscalationEngine(hierarchy=hierarchy)
        # Appeals level allows conflicting_precedents
        result = engine.check_escalation(evaluation, JudicialLevel.appeals)
        assert result.should_escalate
        assert any("conflicting_precedents" in t for t in result.triggers)

    def test_content_trigger_constitutional(
        self, hierarchy: JudicialHierarchy
    ) -> None:
        """Detect constitutional questions in evaluation text."""
        evaluation = CourtEvaluation(
            escalation_recommendation="no_escalation",
            reconciled_decision="This raises a constitutional question about free speech.",
            reasoning_trace=["Constitutional issue found"],
        )
        engine = EscalationEngine(hierarchy=hierarchy)
        # Appeals level allows constitutional escalation
        result = engine.check_escalation(evaluation, JudicialLevel.appeals)
        assert result.should_escalate
        assert any("Constitutional question" in t for t in result.triggers)

    def test_content_trigger_conflicting_precedents(
        self, hierarchy: JudicialHierarchy
    ) -> None:
        evaluation = CourtEvaluation(
            escalation_recommendation="no_escalation",
            reconciled_decision="There is a conflicting precedent from a sister court.",
            reasoning_trace=["Precedent analysis"],
        )
        engine = EscalationEngine(hierarchy=hierarchy)
        result = engine.check_escalation(evaluation, JudicialLevel.appeals)
        assert result.should_escalate

    def test_content_trigger_procedural_irregularity(
        self, hierarchy: JudicialHierarchy
    ) -> None:
        evaluation = CourtEvaluation(
            escalation_recommendation="no_escalation",
            reconciled_decision="A procedural irregularity was identified.",
            reasoning_trace=["Procedural review"],
        )
        engine = EscalationEngine(hierarchy=hierarchy)
        # First instance allows procedural irregularity escalation? No, it doesn't.
        result = engine.check_escalation(
            evaluation, JudicialLevel.first_instance
        )
        assert not result.should_escalate  # first_instance doesn't have this criterion

    def test_no_content_triggers_without_matching_criteria(
        self, hierarchy: JudicialHierarchy
    ) -> None:
        """First instance doesn't allow constitutional escalation via content."""
        evaluation = CourtEvaluation(
            escalation_recommendation="no_escalation",
            reconciled_decision="This raises a constitutional question.",
            reasoning_trace=["Review"],
        )
        engine = EscalationEngine(hierarchy=hierarchy)
        result = engine.check_escalation(
            evaluation, JudicialLevel.first_instance
        )
        # First instance doesn't have constitutional_questions=True
        assert not result.should_escalate

    def test_execute_escalation(
        self,
        hierarchy: JudicialHierarchy,
        folder_manager: CaseFolderManager,
        sample_case: Case,
        escalation_evaluation: CourtEvaluation,
    ) -> None:
        folder_manager.create(sample_case)
        # Create a dummy output file to be archived
        folder_manager.save_output(
            sample_case.id,
            "court_evaluation.json",
            {"test": "data"},
        )

        engine = EscalationEngine(
            hierarchy=hierarchy, folder_manager=folder_manager
        )
        esc_result = EscalationResult(
            should_escalate=True,
            reason="Constitutional question",
            current_level=JudicialLevel.first_instance,
            next_level=JudicialLevel.appeals,
            triggers=["Constitutional question detected"],
        )

        updated = engine.execute_escalation(
            sample_case, escalation_evaluation, esc_result
        )

        assert updated.judicial_level == JudicialLevel.appeals
        assert updated.status == CaseStatus.escalated

        # Check archive was created
        archive_dir = (
            folder_manager.case_dir(sample_case.id)
            / "outputs"
            / "level_first_instance"
        )
        assert archive_dir.exists()
        assert (archive_dir / "court_evaluation.json").exists()

        # Check escalation record was saved
        esc_file = (
            folder_manager.case_dir(sample_case.id)
            / "outputs"
            / "escalation_first_instance.json"
        )
        assert esc_file.exists()
        record: dict[str, object] = json.loads(esc_file.read_text())
        assert record["from_level"] == "First Instance"
        assert record["to_level"] == "Appeals Court"

    def test_execute_escalation_no_escalation(
        self,
        hierarchy: JudicialHierarchy,
        sample_case: Case,
        sample_evaluation: CourtEvaluation,
    ) -> None:
        engine = EscalationEngine(hierarchy=hierarchy)
        esc_result = EscalationResult(
            should_escalate=False,
            reason="No criteria met",
            current_level=JudicialLevel.first_instance,
        )
        updated = engine.execute_escalation(
            sample_case, sample_evaluation, esc_result
        )
        assert updated.judicial_level == JudicialLevel.first_instance
        assert updated.status == CaseStatus.pending  # unchanged

    def test_execute_escalation_updates_case_file(
        self,
        hierarchy: JudicialHierarchy,
        folder_manager: CaseFolderManager,
        sample_case: Case,
        escalation_evaluation: CourtEvaluation,
    ) -> None:
        folder_manager.create(sample_case)
        engine = EscalationEngine(
            hierarchy=hierarchy, folder_manager=folder_manager
        )
        esc_result = EscalationResult(
            should_escalate=True,
            reason="Escalation needed",
            current_level=JudicialLevel.first_instance,
            next_level=JudicialLevel.appeals,
            triggers=["Test trigger"],
        )

        engine.execute_escalation(sample_case, escalation_evaluation, esc_result)

        # Reload case and verify it was updated
        reloaded = folder_manager.load(sample_case.id)
        assert reloaded.judicial_level == JudicialLevel.appeals
        assert reloaded.status == CaseStatus.escalated

    def test_prepare_escalation_context(
        self,
        hierarchy: JudicialHierarchy,
        sample_case: Case,
        escalation_evaluation: CourtEvaluation,
    ) -> None:
        engine = EscalationEngine(hierarchy=hierarchy)
        esc_result = EscalationResult(
            should_escalate=True,
            reason="Constitutional question",
            current_level=JudicialLevel.first_instance,
            next_level=JudicialLevel.appeals,
            triggers=["Constitutional question detected"],
        )

        context = engine.prepare_escalation_context(
            sample_case, escalation_evaluation, esc_result
        )

        assert context["judicial_level"] == "Appeals Court"
        assert "jurisdiction_scope" in context
        assert "procedural_requirements" in context
        assert context["previous_level"] == "First Instance"
        assert context["previous_decision"] == escalation_evaluation.reconciled_decision
        assert "higher_court_instructions" in context
        instructions = str(context["higher_court_instructions"])
        assert "Appeals Court" in instructions
        assert "Constitutional question" in instructions

    def test_prepare_escalation_context_no_next_level(
        self,
        hierarchy: JudicialHierarchy,
        sample_case: Case,
        sample_evaluation: CourtEvaluation,
    ) -> None:
        engine = EscalationEngine(hierarchy=hierarchy)
        esc_result = EscalationResult(
            should_escalate=False,
            reason="No escalation",
            current_level=JudicialLevel.supreme,
        )
        context = engine.prepare_escalation_context(
            sample_case, sample_evaluation, esc_result
        )
        assert context == {}

    def test_full_escalation_flow(
        self,
        hierarchy: JudicialHierarchy,
        folder_manager: CaseFolderManager,
    ) -> None:
        """End-to-end: check -> execute -> prepare context."""
        case = Case(
            id="flow-test",
            title="Full Flow Test",
            facts="Test facts",
        )
        folder_manager.create(case)
        folder_manager.save_output(
            case.id, "court_evaluation.json", {"test": "data"}
        )

        evaluation = CourtEvaluation(
            consistency_scores={"claimant": 0.7, "respondent": 0.5},
            compliance_assessment={"claimant": "OK", "respondent": "OK"},
            preliminary_opinion="Claimant prevails.",
            adversarial_challenge="But there is a conflicting precedent.",
            reconciled_decision="Need higher court for conflicting precedent.",
            escalation_recommendation="escalate_conflicting_precedents",
            reasoning_trace=["Conflicting precedent found between circuits"],
        )

        engine = EscalationEngine(
            hierarchy=hierarchy, folder_manager=folder_manager
        )

        # Step 1: Check
        result = engine.check_escalation(evaluation, JudicialLevel.appeals)
        assert result.should_escalate
        assert result.next_level == JudicialLevel.superior

        # Step 2: Execute
        updated_case = engine.execute_escalation(case, evaluation, result)
        assert updated_case.judicial_level == JudicialLevel.superior
        assert updated_case.status == CaseStatus.escalated

        # Step 3: Prepare context
        context = engine.prepare_escalation_context(
            updated_case, evaluation, result
        )
        assert context["judicial_level"] == "Superior Court"
        assert "conflicting" in str(context["escalation_reason"]).lower()
