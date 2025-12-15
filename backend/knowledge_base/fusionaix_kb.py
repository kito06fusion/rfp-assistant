from __future__ import annotations

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Capability:
    name: str
    description: str
    technologies: List[str]
    industries: List[str]
    key_differentiators: List[str]


@dataclass
class CaseStudy:
    title: str
    client_industry: str
    challenge: str
    solution: str
    technologies_used: List[str]
    outcomes: List[str]
    relevance_keywords: List[str]  # Keywords for matching to requirements


@dataclass
class Accelerator:
    name: str
    description: str
    use_cases: List[str]
    benefits: List[str]


class FusionAIxKnowledgeBase:
    
    def __init__(self):
        self.capabilities = self._load_capabilities()
        self.case_studies = self._load_case_studies()
        self.accelerators = self._load_accelerators()
        self.company_overview = self._get_company_overview()
        self.key_differentiators = self._get_key_differentiators()
    
    def _load_capabilities(self) -> List[Capability]:
        """Load fusionAIx capabilities."""
        return [
            Capability(
                name="Pega Constellation Expertise",
                description=(
                    "Specialized expertise in Pega Constellation platform with 20+ global implementations. "
                    "Deep knowledge of Constellation architecture, DX components, and modernization strategies."
                ),
                technologies=["Pega Constellation", "Pega Platform", "DX Components"],
                industries=["Insurance", "Banking", "Financial Services", "Government", "Healthcare"],
                key_differentiators=[
                    "20+ Pega Constellation implementations globally",
                    "AI-powered Constellation Center of Excellence",
                    "Niche Constellation specialist positioning",
                    "Proven track record in Constellation modernization"
                ]
            ),
            Capability(
                name="Microsoft Power Platform",
                description=(
                    "Comprehensive Power Platform implementation and advisory services including Power Apps, "
                    "Power Automate, Power BI, and Power Virtual Agents."
                ),
                technologies=["Power Apps", "Power Automate", "Power BI", "Power Virtual Agents"],
                industries=["Insurance", "Banking", "Financial Services", "Government", "Healthcare"],
                key_differentiators=[
                    "End-to-end Power Platform solutions",
                    "Integration with existing enterprise systems",
                    "Rapid application development expertise"
                ]
            ),
            Capability(
                name="ServiceNow Implementation",
                description=(
                    "ServiceNow platform implementation, customization, and optimization services "
                    "for IT service management, workflow automation, and digital transformation."
                ),
                technologies=["ServiceNow", "ITSM", "Workflow Automation"],
                industries=["Insurance", "Banking", "Financial Services", "Government", "Healthcare"],
                key_differentiators=[
                    "ServiceNow certified expertise",
                    "Custom application development",
                    "Process optimization and automation"
                ]
            ),
            Capability(
                name="Low-Code Development",
                description=(
                    "Low-code and no-code platform expertise enabling rapid application development "
                    "and digital transformation with reduced time-to-market."
                ),
                technologies=["Low-Code Platforms", "Rapid Application Development"],
                industries=["Insurance", "Banking", "Financial Services", "Government", "Healthcare"],
                key_differentiators=[
                    "Accelerated delivery through platform-led automation",
                    "Proven low-code methodologies",
                    "Modernization of legacy workflows"
                ]
            ),
            Capability(
                name="AI-Driven Solutions",
                description=(
                    "AI-powered solutions and accelerators including AI Studio, intelligent automation, "
                    "and AI-enhanced development capabilities."
                ),
                technologies=["AI/ML", "Intelligent Automation", "AI Studio"],
                industries=["Insurance", "Banking", "Financial Services", "Government", "Healthcare"],
                key_differentiators=[
                    "AI-powered Constellation Center of Excellence",
                    "fxAIStudio for AI-enhanced development",
                    "Intelligent automation capabilities"
                ]
            ),
        ]
    
    def _load_case_studies(self) -> List[CaseStudy]:
        """Load fusionAIx case studies."""
        return [
            CaseStudy(
                title="Pega Constellation Modernization - Insurance",
                client_industry="Insurance",
                challenge=(
                    "Legacy BPM system requiring modernization to Constellation architecture "
                    "with improved user experience and faster time-to-market for new products."
                ),
                solution=(
                    "Implemented Pega Constellation platform with custom DX components, "
                    "modernized existing case management workflows, and established AI-powered "
                    "development practices. Delivered 20+ reusable components."
                ),
                technologies_used=["Pega Constellation", "DX Components", "AI Studio"],
                outcomes=[
                    "Reduced time-to-market for new products by 40%",
                    "Improved user experience with modern Constellation UI",
                    "Established reusable component library",
                    "Accelerated development through AI-powered CoE"
                ],
                relevance_keywords=[
                    "Pega", "Constellation", "BPM", "case management", "workflow",
                    "modernization", "insurance", "user experience", "time-to-market"
                ]
            ),
            CaseStudy(
                title="Enterprise Workflow Automation - Financial Services",
                client_industry="Banking/Financial Services",
                challenge=(
                    "Complex manual processes requiring automation and integration with multiple "
                    "legacy systems while maintaining compliance and security standards."
                ),
                solution=(
                    "Designed and implemented automated workflow solution using Pega Platform "
                    "with integration to core banking systems, document management, and identity management. "
                    "Leveraged fxAgentSDK for rapid integration development."
                ),
                technologies_used=["Pega Platform", "System Integration", "Workflow Automation"],
                outcomes=[
                    "Automated 15+ manual processes",
                    "Reduced processing time by 60%",
                    "Improved compliance through automated controls",
                    "Enhanced customer experience with faster turnaround"
                ],
                relevance_keywords=[
                    "automation", "workflow", "integration", "legacy systems",
                    "financial services", "banking", "compliance", "security"
                ]
            ),
            CaseStudy(
                title="Digital Transformation - Government",
                client_industry="Government",
                challenge=(
                    "Citizen service portal requiring modernization with improved accessibility, "
                    "multi-language support, and streamlined case processing."
                ),
                solution=(
                    "Implemented Pega Constellation solution with fxTranslate for localization, "
                    "custom DX components for citizen services, and integration with government systems. "
                    "Delivered responsive, accessible interface."
                ),
                technologies_used=["Pega Constellation", "Localization", "DX Components", "Government Integration"],
                outcomes=[
                    "Improved citizen satisfaction scores by 35%",
                    "Reduced case processing time by 50%",
                    "Enabled multi-language support",
                    "Enhanced accessibility compliance"
                ],
                relevance_keywords=[
                    "government", "citizen services", "digital transformation",
                    "localization", "accessibility", "case processing", "portal"
                ]
            ),
        ]
    
    def _load_accelerators(self) -> List[Accelerator]:
        """Load fusionAIx accelerators and tools."""
        return [
            Accelerator(
                name="fxAgentSDK",
                description=(
                    "Proprietary SDK for rapid development of Pega agents and integrations. "
                    "Accelerates integration with external systems and reduces development time."
                ),
                use_cases=[
                    "System integrations",
                    "Agent development",
                    "API connectivity",
                    "Legacy system modernization"
                ],
                benefits=[
                    "Reduced integration development time by 50%",
                    "Standardized integration patterns",
                    "Improved maintainability",
                    "Faster time-to-value"
                ]
            ),
            Accelerator(
                name="fxAIStudio",
                description=(
                    "AI-powered development studio for accelerating DX component creation and "
                    "modernization outcomes. Enhances developer productivity through AI assistance."
                ),
                use_cases=[
                    "DX component development",
                    "Code generation",
                    "Modernization projects",
                    "Rapid prototyping"
                ],
                benefits=[
                    "Accelerated component development",
                    "AI-powered code suggestions",
                    "Improved code quality",
                    "Faster modernization cycles"
                ]
            ),
            Accelerator(
                name="fxMockUpToView",
                description=(
                    "Tool for converting mockups and designs directly into Pega views. "
                    "Streamlines UI development and reduces design-to-implementation time."
                ),
                use_cases=[
                    "UI development",
                    "Design implementation",
                    "Rapid prototyping",
                    "View creation"
                ],
                benefits=[
                    "Faster UI development",
                    "Design-to-code automation",
                    "Improved design fidelity",
                    "Reduced rework"
                ]
            ),
            Accelerator(
                name="fxSmartDCO",
                description=(
                    "Intelligent Direct Capture of Objectives (DCO) tool for Pega. "
                    "Enhances requirements capture and accelerates application development."
                ),
                use_cases=[
                    "Requirements capture",
                    "Application design",
                    "DCO enhancement",
                    "Rapid development"
                ],
                benefits=[
                    "Improved requirements accuracy",
                    "Faster application development",
                    "Enhanced DCO capabilities",
                    "Reduced design iterations"
                ]
            ),
            Accelerator(
                name="fxTranslate",
                description=(
                    "Pega Marketplace offering for Constellation localization support. "
                    "Enables multi-language support for Constellation applications."
                ),
                use_cases=[
                    "Multi-language support",
                    "Localization",
                    "International deployments",
                    "Constellation applications"
                ],
                benefits=[
                    "Simplified localization",
                    "Reduced translation effort",
                    "Consistent multi-language experience",
                    "Faster international rollouts"
                ]
            ),
        ]
    
    def _get_company_overview(self) -> str:
        """Get company overview text."""
        return """fusionAIx is a specialized low-code and AI-driven digital transformation partner focused on modernizing enterprise workflows, improving customer/employee experiences, and accelerating delivery through platform-led automation. The company was established in 2023, with active entities including a UK-based consultancy (incorporated 3 August 2023) and an India-based technology arm (incorporated 20 July 2023).

With proven capabilities across Pega Constellation, Microsoft Power Platform, and ServiceNow, fusionAIx provides advisory, modernization, implementation, and managed delivery services designed to meet enterprise requirements for scalability, security, and governance.

In the Pega ecosystem, fusionAIx positions itself as a niche Constellation specialist and states it has delivered 20+ Pega Constellation implementations globally. The company also highlights an AI-powered Constellation Center of Excellence aimed at accelerating DX component creation and modernization outcomes.

To speed time-to-value, fusionAIx offers proprietary accelerators and solution components such as fxAgentSDK, fxAIStudio, fxMockUpToView, and fxSmartDCO, alongside Pega Marketplace offerings like fxTranslate for Constellation localization support.

The firm supports clients across industries including insurance, banking/financial services, government, and healthcare, combining platform expertise with structured knowledge transfer to help customers build sustainable, future-ready capabilities."""
    
    def _get_key_differentiators(self) -> List[str]:
        """Get key differentiators."""
        return [
            "20+ Pega Constellation implementations globally",
            "AI-powered Constellation Center of Excellence",
            "Niche Constellation specialist positioning",
            "Proprietary accelerators (fxAgentSDK, fxAIStudio, fxMockUpToView, fxSmartDCO)",
            "Pega Marketplace offerings (fxTranslate)",
            "Proven track record across insurance, banking, government, and healthcare",
            "Established in 2023 with UK and India entities",
            "Focus on platform-led automation and rapid delivery",
            "Structured knowledge transfer and capability building",
            "Combination of advisory, implementation, and managed delivery services"
        ]
    
    def get_relevant_capabilities(self, requirement_text: str) -> List[Capability]:
        """Get capabilities relevant to a requirement."""
        requirement_lower = requirement_text.lower()
        relevant = []
        
        for capability in self.capabilities:
            if any(tech.lower() in requirement_lower for tech in capability.technologies):
                relevant.append(capability)
            elif any(ind.lower() in requirement_lower for ind in capability.industries):
                relevant.append(capability)
            elif any(diff.lower() in requirement_lower for diff in capability.key_differentiators):
                relevant.append(capability)
        
        return relevant if relevant else self.capabilities[:2]  # Return top 2 if no match
    
    def get_relevant_case_studies(self, requirement_text: str, max_results: int = 2) -> List[CaseStudy]:
        """Get case studies relevant to a requirement."""
        requirement_lower = requirement_text.lower()
        scored_studies = []
        
        for study in self.case_studies:
            score = 0
            for keyword in study.relevance_keywords:
                if keyword.lower() in requirement_lower:
                    score += 1
            if study.client_industry.lower() in requirement_lower:
                score += 2
            for tech in study.technologies_used:
                if tech.lower() in requirement_lower:
                    score += 1
            
            if score > 0:
                scored_studies.append((score, study))
        
        scored_studies.sort(reverse=True, key=lambda x: x[0])
        return [study for _, study in scored_studies[:max_results]]
    
    def get_relevant_accelerators(self, requirement_text: str) -> List[Accelerator]:
        """Get accelerators relevant to a requirement."""
        requirement_lower = requirement_text.lower()
        relevant = []
        
        for accelerator in self.accelerators:
            if accelerator.name.lower() in requirement_lower:
                relevant.append(accelerator)
            elif any(use_case.lower() in requirement_lower for use_case in accelerator.use_cases):
                relevant.append(accelerator)
        
        return relevant if relevant else self.accelerators[:2]  # Return top 2 if no match
    
    def format_for_prompt(self, requirement_text: str) -> str:
        """Format knowledge base content for inclusion in LLM prompts."""
        parts = []
        
        parts.append("FUSIONAIX COMPANY OVERVIEW:")
        parts.append("=" * 80)
        parts.append(self.company_overview)
        parts.append("")
        
        relevant_caps = self.get_relevant_capabilities(requirement_text)
        if relevant_caps:
            parts.append("RELEVANT FUSIONAIX CAPABILITIES:")
            parts.append("-" * 80)
            for cap in relevant_caps:
                parts.append(f"• {cap.name}")
                parts.append(f"  {cap.description}")
                parts.append(f"  Technologies: {', '.join(cap.technologies)}")
                parts.append(f"  Industries: {', '.join(cap.industries)}")
                if cap.key_differentiators:
                    parts.append(f"  Key Points: {', '.join(cap.key_differentiators[:3])}")
                parts.append("")
        
        relevant_studies = self.get_relevant_case_studies(requirement_text)
        if relevant_studies:
            parts.append("RELEVANT FUSIONAIX CASE STUDIES:")
            parts.append("-" * 80)
            for study in relevant_studies:
                parts.append(f"• {study.title} ({study.client_industry})")
                parts.append(f"  Challenge: {study.challenge}")
                parts.append(f"  Solution: {study.solution}")
                parts.append(f"  Technologies: {', '.join(study.technologies_used)}")
                parts.append(f"  Outcomes: {', '.join(study.outcomes)}")
                parts.append("")
        
        relevant_accels = self.get_relevant_accelerators(requirement_text)
        if relevant_accels:
            parts.append("RELEVANT FUSIONAIX ACCELERATORS:")
            parts.append("-" * 80)
            for accel in relevant_accels:
                parts.append(f"• {accel.name}")
                parts.append(f"  {accel.description}")
                parts.append(f"  Use Cases: {', '.join(accel.use_cases)}")
                parts.append(f"  Benefits: {', '.join(accel.benefits[:2])}")
                parts.append("")
        
        parts.append("FUSIONAIX KEY DIFFERENTIATORS:")
        parts.append("-" * 80)
        for diff in self.key_differentiators[:5]:  # Top 5
            parts.append(f"• {diff}")
        parts.append("")
        
        return "\n".join(parts)
    
    def get_summary_for_rag(self) -> str:
        """Get a summary suitable for RAG indexing."""
        parts = [self.company_overview]
        parts.append("\n\nKey Capabilities:")
        for cap in self.capabilities:
            parts.append(f"- {cap.name}: {cap.description}")
        parts.append("\n\nCase Studies:")
        for study in self.case_studies:
            parts.append(f"- {study.title}: {study.solution}")
        parts.append("\n\nAccelerators:")
        for accel in self.accelerators:
            parts.append(f"- {accel.name}: {accel.description}")
        return "\n".join(parts)
