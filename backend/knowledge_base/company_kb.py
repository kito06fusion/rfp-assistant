from __future__ import annotations

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CompanyInfo:
    """Hardcoded company information."""
    # Platform/Technology Stack
    primary_platforms: List[str]
    secondary_platforms: List[str]
    technologies: List[str]
    
    # Company Details
    company_name: str
    website: str
    established_year: str
    entities: List[str]
    
    # Certifications
    certifications: List[str]
    
    # Pricing Models
    pricing_models: List[str]
    pricing_approach: str
    
    # Standard Processes
    standard_processes: List[str]
    methodologies: List[str]
    
    # Contact Information
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    
    # Other Known Information
    other_info: Dict[str, Any] = None


class CompanyKnowledgeBase:
    """Knowledge base for hardcoded company values that should not trigger questions."""
    
    def __init__(self):
        self.info = self._load_company_info()
        logger.info("Company knowledge base loaded with %d platforms, %d certifications", 
                   len(self.info.primary_platforms), len(self.info.certifications))
    
    def _load_company_info(self) -> CompanyInfo:
        """Load hardcoded company information."""
        return CompanyInfo(
            # Platform/Technology Stack
            primary_platforms=[
                "Pega Constellation",
                "Pega Platform",
            ],
            secondary_platforms=[
                "Microsoft Power Platform",
                "ServiceNow",
            ],
            technologies=[
                "Pega Constellation",
                "Pega Platform",
                "DX Components",
                "Power Apps",
                "Power Automate",
                "Power BI",
                "ServiceNow",
                "Low-Code Platforms",
                "AI/ML",
                "Intelligent Automation",
            ],
            
            # Company Details
            company_name="fusionAIx",
            website="fusionaix.com",
            established_year="2023",
            entities=[
                "UK-based consultancy (incorporated 3 August 2023)",
                "India-based technology arm (incorporated 20 July 2023)",
            ],
            
            certifications=[
                "Pega Certified",
            ],
            
            pricing_models=[
                "Fixed Price",
                "Time and Materials",
                "Managed Services",
            ],
            pricing_approach=(
                "fusionAIx offers flexible pricing models including fixed price for well-defined projects, "
                "time and materials for agile development, and managed services for ongoing support. "
                "Pricing is tailored to project scope, timeline, and client requirements."
            ),
            
            # Standard Processes
            standard_processes=[
                "Agile/Scrum methodology",
                "Structured knowledge transfer",
                "Platform-led automation",
                "AI-powered development practices",
            ],
            methodologies=[
                "Agile/Scrum",
                "Rapid Application Development",
                "Low-Code Development",
                "Modernization Strategies",
            ],
            
            # Other Known Information
            other_info={
                "pega_constellation_implementations": "20+",
                "industries_served": ["Insurance", "Banking/Financial Services", "Government", "Healthcare"],
                "services": ["Advisory", "Modernization", "Implementation", "Managed Delivery"],
            },
        )
    
    def has_info(self, topic: str) -> bool:
        """Check if we have information about a topic."""
        topic_lower = topic.lower()
        
        # Check platforms
        all_platforms = self.info.primary_platforms + self.info.secondary_platforms
        if any(platform.lower() in topic_lower for platform in all_platforms):
            return True
        
        # Check technologies
        if any(tech.lower() in topic_lower for tech in self.info.technologies):
            return True
        
        # Check certifications
        if any(cert.lower() in topic_lower for cert in self.info.certifications):
            return True
        
        # Check pricing
        if any(keyword in topic_lower for keyword in ["pricing", "cost", "price", "budget", "fee"]):
            return True
        
        # Check processes/methodologies
        if any(proc.lower() in topic_lower for proc in self.info.standard_processes):
            return True
        if any(meth.lower() in topic_lower for meth in self.info.methodologies):
            return True
        
        # Check company details
        if any(keyword in topic_lower for keyword in ["company", "firm", "organization", "vendor"]):
            return True
        
        return False
    
    def get_info(self, topic: str) -> Optional[str]:
        """Get information about a topic if available."""
        topic_lower = topic.lower()
        
        # Platform information
        all_platforms = self.info.primary_platforms + self.info.secondary_platforms
        for platform in all_platforms:
            if platform.lower() in topic_lower:
                if platform in self.info.primary_platforms:
                    return f"fusionAIx's primary platform is {platform}. We have 20+ implementations globally."
                else:
                    return f"fusionAIx also works with {platform}."
        
        # Technology information
        for tech in self.info.technologies:
            if tech.lower() in topic_lower:
                return f"fusionAIx has expertise in {tech}."
        
        # Pricing information
        if any(keyword in topic_lower for keyword in ["pricing", "cost", "price", "budget", "fee"]):
            return self.info.pricing_approach
        
        # Certification information
        if any(keyword in topic_lower for keyword in ["certification", "certified", "cert"]):
            if self.info.certifications:
                return f"fusionAIx holds the following certifications: {', '.join(self.info.certifications)}."
            return "Certification information is available upon request."
        
        # Process/methodology information
        for proc in self.info.standard_processes:
            if proc.lower() in topic_lower:
                return f"fusionAIx uses {proc} as a standard process."
        
        for meth in self.info.methodologies:
            if meth.lower() in topic_lower:
                return f"fusionAIx employs {meth} methodology."
        
        # Company information
        if any(keyword in topic_lower for keyword in ["company", "firm", "organization", "vendor"]):
            return f"{self.info.company_name} ({self.info.website}) was established in {self.info.established_year}."
        
        return None
    
    def get_all_known_topics(self) -> List[str]:
        """Get list of all topics we have information about."""
        topics = []
        topics.extend(self.info.primary_platforms)
        topics.extend(self.info.secondary_platforms)
        topics.extend(self.info.technologies)
        topics.extend(self.info.certifications)
        topics.extend(["pricing", "cost", "price"])
        topics.extend(self.info.standard_processes)
        topics.extend(self.info.methodologies)
        topics.extend(["company", "firm", "organization"])
        return topics
    
    def format_for_prompt(self) -> str:
        """Format company knowledge base for inclusion in prompts."""
        parts = []
        parts.append("KNOWN COMPANY INFORMATION (Do NOT ask questions about these):")
        parts.append("=" * 80)
        parts.append(f"Company: {self.info.company_name} ({self.info.website})")
        parts.append(f"Established: {self.info.established_year}")
        parts.append("")
        parts.append("Primary Platforms:")
        for platform in self.info.primary_platforms:
            parts.append(f"  - {platform}")
        parts.append("")
        parts.append("Secondary Platforms:")
        for platform in self.info.secondary_platforms:
            parts.append(f"  - {platform}")
        parts.append("")
        parts.append("Technologies:")
        for tech in self.info.technologies:
            parts.append(f"  - {tech}")
        parts.append("")
        if self.info.certifications:
            parts.append("Certifications:")
            for cert in self.info.certifications:
                parts.append(f"  - {cert}")
            parts.append("")
        parts.append("Pricing Approach:")
        parts.append(f"  {self.info.pricing_approach}")
        parts.append("")
        parts.append("Standard Processes:")
        for proc in self.info.standard_processes:
            parts.append(f"  - {proc}")
        parts.append("")
        return "\n".join(parts)

