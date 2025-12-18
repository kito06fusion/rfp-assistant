from __future__ import annotations

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CompanyInfo:
    primary_platforms: List[str]
    secondary_platforms: List[str]
    technologies: List[str]
    
    company_name: str
    website: str
    established_year: str
    entities: List[str]
    
    certifications: List[str]
    
    pricing_models: List[str]
    pricing_approach: str
    
    standard_processes: List[str]
    methodologies: List[str]
    
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    
    other_info: Dict[str, Any] = None


class CompanyKnowledgeBase:    
    def __init__(self):
        self.info = self._load_company_info()
        logger.info("Company knowledge base loaded with %d platforms, %d certifications", 
                   len(self.info.primary_platforms), len(self.info.certifications))
    
    def _load_company_info(self) -> CompanyInfo:
        return CompanyInfo(
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
            
            company_name="fusionAIx",
            website="www.fusionaix.com",
            established_year="2023",
            entities=[
                "UK-based consultancy (incorporated 3 August 2023)",
                "India-based technology arm (incorporated 20 July 2023)",
            ],
            contact_email="contact@fusionaix.com",
            
            certifications=[
                "Pega Certified",
                "Great Place To Work® Certified Company (2025–26)",
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
            
            other_info={
                "pega_constellation_implementations": "20+",
                "industries_served": [
                    "Insurance",
                    "Banking & Finance",
                    "Government & Public Sector",
                    "Automotive & Fleet Management",
                    "Travel & Tourism"
                ],
                "services": [
                    "Low Code/No Code",
                    "Digital Process Transformation",
                    "AI & Data"
                ],
            },
        )
    
    def has_info(self, topic: str) -> bool:
        topic_lower = topic.lower()
        
        all_platforms = self.info.primary_platforms + self.info.secondary_platforms
        if any(platform.lower() in topic_lower for platform in all_platforms):
            return True
        
        if any(tech.lower() in topic_lower for tech in self.info.technologies):
            return True
        
        if any(cert.lower() in topic_lower for cert in self.info.certifications):
            return True
        
        if any(keyword in topic_lower for keyword in ["pricing", "cost", "price", "budget", "fee"]):
            return True

        if any(proc.lower() in topic_lower for proc in self.info.standard_processes):
            return True
        if any(meth.lower() in topic_lower for meth in self.info.methodologies):
            return True
        
        if any(keyword in topic_lower for keyword in ["company", "firm", "organization", "vendor"]):
            return True
        
        return False
    
    def get_info(self, topic: str) -> Optional[str]:
        topic_lower = topic.lower()
        
        all_platforms = self.info.primary_platforms + self.info.secondary_platforms
        for platform in all_platforms:
            if platform.lower() in topic_lower:
                if platform in self.info.primary_platforms:
                    return f"fusionAIx's primary platform is {platform}. We have 20+ implementations globally."
                else:
                    return f"fusionAIx also works with {platform}."
        
        for tech in self.info.technologies:
            if tech.lower() in topic_lower:
                return f"fusionAIx has expertise in {tech}."
        
        if any(keyword in topic_lower for keyword in ["pricing", "cost", "price", "budget", "fee"]):
            return self.info.pricing_approach
        
        if any(keyword in topic_lower for keyword in ["certification", "certified", "cert"]):
            if self.info.certifications:
                return f"fusionAIx holds the following certifications: {', '.join(self.info.certifications)}."
            return "Certification information is available upon request."
        
        for proc in self.info.standard_processes:
            if proc.lower() in topic_lower:
                return f"fusionAIx uses {proc} as a standard process."
        
        for meth in self.info.methodologies:
            if meth.lower() in topic_lower:
                return f"fusionAIx employs {meth} methodology."
        
        if any(keyword in topic_lower for keyword in ["company", "firm", "organization", "vendor"]):
            return f"{self.info.company_name} ({self.info.website}) was established in {self.info.established_year}."
        
        return None
    
    def get_all_known_topics(self) -> List[str]:
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

