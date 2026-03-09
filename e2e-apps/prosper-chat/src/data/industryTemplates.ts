import {
  Sparkles, Stethoscope, Car, Scissors, Dumbbell,
  Home, UtensilsCrossed, Scale, Wrench, PawPrint,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export interface TemplateService {
  name: string;
  duration_minutes: number;
  price_text: string;
  description?: string;
}

export interface TemplateFaq {
  question: string;
  answer: string;
}

export interface IndustryTemplate {
  id: string;
  name: string;
  icon: LucideIcon;
  services: TemplateService[];
  faqs: TemplateFaq[];
}

export const industryTemplates: IndustryTemplate[] = [
  {
    id: "spa-wellness",
    name: "Spa / Wellness",
    icon: Sparkles,
    services: [
      { name: "Deep Tissue Massage", duration_minutes: 60, price_text: "$120", description: "Full-body deep tissue massage for tension relief" },
      { name: "Signature Facial", duration_minutes: 45, price_text: "$95", description: "Customized facial with cleanse, exfoliation & mask" },
      { name: "Hot Stone Therapy", duration_minutes: 75, price_text: "$140", description: "Heated basalt stones combined with massage technique" },
      { name: "Aromatherapy Session", duration_minutes: 60, price_text: "$110", description: "Essential oil-infused relaxation massage" },
    ],
    faqs: [
      { question: "What are your hours?", answer: "We're open Monday–Saturday, 9 AM to 7 PM. Closed on Sundays." },
      { question: "What's your cancellation policy?", answer: "We require 24-hour notice for cancellations. Late cancellations may incur a 50% charge." },
      { question: "What should I bring to my appointment?", answer: "Just yourself! We provide robes, slippers, and all necessary products. Arrive 10 minutes early to relax." },
      { question: "Do you offer couples services?", answer: "Yes! We have a dedicated couples suite for side-by-side massages and facials." },
    ],
  },
  {
    id: "dental",
    name: "Dental Office",
    icon: Stethoscope,
    services: [
      { name: "Dental Cleaning", duration_minutes: 45, price_text: "$150", description: "Professional teeth cleaning and polishing" },
      { name: "Teeth Whitening", duration_minutes: 60, price_text: "$350", description: "In-office professional whitening treatment" },
      { name: "Emergency Exam", duration_minutes: 30, price_text: "$100", description: "Urgent evaluation for dental pain or injury" },
      { name: "Comprehensive Exam", duration_minutes: 60, price_text: "$200", description: "Full oral examination with X-rays" },
    ],
    faqs: [
      { question: "Do you accept insurance?", answer: "Yes, we accept most major dental insurance plans. Contact us to verify your specific coverage." },
      { question: "What should I expect at my first visit?", answer: "Your first visit includes a comprehensive exam, X-rays, and a treatment plan discussion. Please arrive 15 minutes early to complete paperwork." },
      { question: "Is teeth whitening painful?", answer: "Most patients experience little to no discomfort. Some sensitivity is normal for 24–48 hours after treatment." },
      { question: "Do you offer payment plans?", answer: "Yes, we offer flexible payment plans and accept CareCredit for treatments not fully covered by insurance." },
    ],
  },
  {
    id: "auto-repair",
    name: "Auto Repair",
    icon: Car,
    services: [
      { name: "Oil Change", duration_minutes: 30, price_text: "$45", description: "Conventional or synthetic oil change with filter" },
      { name: "Brake Inspection", duration_minutes: 45, price_text: "$60", description: "Complete brake system evaluation" },
      { name: "Tire Rotation", duration_minutes: 30, price_text: "$35", description: "Rotate all four tires for even wear" },
      { name: "Full Diagnostic", duration_minutes: 60, price_text: "$100", description: "Computer diagnostic scan and inspection" },
    ],
    faqs: [
      { question: "Do you provide free estimates?", answer: "Yes, we provide free written estimates before any work begins. No surprises." },
      { question: "Do you accept walk-ins?", answer: "Walk-ins are welcome for quick services like oil changes. For larger repairs, we recommend scheduling ahead." },
      { question: "Do you offer a warranty on repairs?", answer: "Yes, all our repairs come with a 12-month / 12,000-mile warranty on parts and labor." },
      { question: "Can I wait while my car is serviced?", answer: "Absolutely. We have a comfortable waiting area with Wi-Fi and complimentary coffee." },
    ],
  },
  {
    id: "salon-barbershop",
    name: "Salon / Barbershop",
    icon: Scissors,
    services: [
      { name: "Haircut & Style", duration_minutes: 45, price_text: "$55", description: "Precision cut with wash and style" },
      { name: "Color Service", duration_minutes: 90, price_text: "$120", description: "Full color or highlights" },
      { name: "Beard Trim", duration_minutes: 20, price_text: "$25", description: "Shape and trim with hot towel finish" },
      { name: "Blowout", duration_minutes: 30, price_text: "$40", description: "Wash and professional blowout styling" },
    ],
    faqs: [
      { question: "Do I need an appointment?", answer: "Appointments are recommended to guarantee your time slot, but we do accept walk-ins based on availability." },
      { question: "What products do you use?", answer: "We use professional-grade products from brands like Redken, Olaplex, and American Crew." },
      { question: "How much does a haircut cost?", answer: "Haircuts start at $55 for adults. Kids and seniors receive a discount. Color and specialty services are priced separately." },
    ],
  },
  {
    id: "fitness-gym",
    name: "Fitness / Gym",
    icon: Dumbbell,
    services: [
      { name: "Personal Training Session", duration_minutes: 60, price_text: "$80", description: "One-on-one training with certified trainer" },
      { name: "Group Fitness Class", duration_minutes: 45, price_text: "$20", description: "High-energy group workout" },
      { name: "Fitness Assessment", duration_minutes: 30, price_text: "Free", description: "Body composition analysis and goal setting" },
      { name: "Nutrition Consultation", duration_minutes: 45, price_text: "$60", description: "Personalized meal planning session" },
    ],
    faqs: [
      { question: "What memberships do you offer?", answer: "We offer monthly ($49), quarterly ($129), and annual ($449) memberships. All include full gym access and group classes." },
      { question: "What's your cancellation policy?", answer: "Monthly memberships can be cancelled with 30 days notice. No long-term contracts required." },
      { question: "What should I bring?", answer: "Bring a water bottle, towel, and clean athletic shoes. We provide lockers and showers." },
      { question: "Do you offer free trials?", answer: "Yes! First-time visitors get a free 3-day pass to try our facilities." },
    ],
  },
  {
    id: "real-estate",
    name: "Real Estate",
    icon: Home,
    services: [
      { name: "Home Valuation", duration_minutes: 60, price_text: "Free", description: "Comparative market analysis of your property" },
      { name: "Buyer Consultation", duration_minutes: 45, price_text: "Free", description: "Discuss your home search criteria and budget" },
      { name: "Open House Visit", duration_minutes: 30, price_text: "Free", description: "Guided tour of available properties" },
      { name: "Listing Consultation", duration_minutes: 60, price_text: "Free", description: "Strategy session for selling your home" },
    ],
    faqs: [
      { question: "What are your fees?", answer: "Buyer consultations are free. Seller commissions are competitive and discussed during the listing consultation." },
      { question: "How long does it take to buy a home?", answer: "On average, the process takes 30–60 days from offer acceptance to closing, depending on financing and inspections." },
      { question: "Do you help with financing?", answer: "While we're not lenders, we work closely with trusted mortgage partners and can connect you with pre-approval resources." },
    ],
  },
  {
    id: "restaurant-cafe",
    name: "Restaurant / Cafe",
    icon: UtensilsCrossed,
    services: [
      { name: "Catering Service", duration_minutes: 120, price_text: "From $500", description: "Full-service catering for events and gatherings" },
      { name: "Private Event Booking", duration_minutes: 180, price_text: "From $300", description: "Reserve our private dining space" },
      { name: "Delivery Order", duration_minutes: 45, price_text: "Menu prices", description: "Hot food delivered to your door" },
    ],
    faqs: [
      { question: "Do you accommodate food allergies?", answer: "Yes, please inform your server of any allergies. Our kitchen can modify most dishes to accommodate common restrictions." },
      { question: "Do you take reservations?", answer: "Yes! Reservations are recommended for dinner and weekends. You can book online or call us directly." },
      { question: "What are your hours?", answer: "Mon–Thu: 11 AM–9 PM, Fri–Sat: 11 AM–10 PM, Sun: 10 AM–8 PM (brunch starts at 10)." },
      { question: "Do you offer gift cards?", answer: "Yes, gift cards are available in any amount at the register or online." },
    ],
  },
  {
    id: "legal-office",
    name: "Legal Office",
    icon: Scale,
    services: [
      { name: "Initial Consultation", duration_minutes: 60, price_text: "$150", description: "Review your case and discuss legal options" },
      { name: "Document Review", duration_minutes: 45, price_text: "$200", description: "Legal review of contracts or agreements" },
      { name: "Mediation Session", duration_minutes: 120, price_text: "$400", description: "Guided dispute resolution session" },
    ],
    faqs: [
      { question: "How much do you charge?", answer: "Initial consultations are $150. Ongoing representation fees depend on the case type and complexity, discussed upfront." },
      { question: "Is my consultation confidential?", answer: "Absolutely. All communications are protected by attorney-client privilege from the moment of consultation." },
      { question: "What areas of law do you practice?", answer: "We specialize in family law, estate planning, business law, and civil litigation." },
      { question: "How should I prepare for my consultation?", answer: "Bring any relevant documents, a timeline of events, and a list of questions. This helps us use your time effectively." },
    ],
  },
  {
    id: "plumbing-hvac",
    name: "Plumbing / HVAC",
    icon: Wrench,
    services: [
      { name: "Emergency Repair", duration_minutes: 60, price_text: "From $150", description: "24/7 emergency plumbing or HVAC repair" },
      { name: "AC Tune-Up", duration_minutes: 45, price_text: "$99", description: "Seasonal maintenance and efficiency check" },
      { name: "Home Inspection", duration_minutes: 90, price_text: "$175", description: "Complete plumbing and HVAC system inspection" },
      { name: "Water Heater Service", duration_minutes: 60, price_text: "$125", description: "Flush, inspect, and maintain your water heater" },
    ],
    faqs: [
      { question: "How much does a service call cost?", answer: "Standard service calls start at $85. Emergency and after-hours calls have an additional surcharge." },
      { question: "Do you handle emergencies after hours?", answer: "Yes, we offer 24/7 emergency service for plumbing leaks, HVAC failures, and other urgent issues." },
      { question: "Do you guarantee your work?", answer: "All repairs come with a 1-year warranty on labor and we honor all manufacturer warranties on parts." },
    ],
  },
  {
    id: "pet-services",
    name: "Pet Services",
    icon: PawPrint,
    services: [
      { name: "Full Grooming", duration_minutes: 60, price_text: "From $50", description: "Bath, haircut, nail trim, and ear cleaning" },
      { name: "Overnight Boarding", duration_minutes: 1440, price_text: "$45/night", description: "Safe and comfortable overnight stay" },
      { name: "Wellness Checkup", duration_minutes: 30, price_text: "$75", description: "Basic health exam and vaccinations" },
      { name: "Dog Walking", duration_minutes: 30, price_text: "$20", description: "30-minute neighborhood walk" },
    ],
    faqs: [
      { question: "What vaccinations are required?", answer: "All pets must be current on rabies, distemper, and bordetella vaccinations. Please bring proof at drop-off." },
      { question: "What time is drop-off and pick-up?", answer: "Drop-off is between 7–10 AM and pick-up is between 4–7 PM. Early/late arrangements can be made for a small fee." },
      { question: "How much does grooming cost?", answer: "Grooming starts at $50 for small dogs and varies by breed, size, and coat condition. We provide a quote before starting." },
      { question: "Can I visit my pet during boarding?", answer: "Yes, visits are welcome during our open hours. We also send daily photo updates!" },
    ],
  },
];
