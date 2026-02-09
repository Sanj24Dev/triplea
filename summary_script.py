import argparse
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Image, Spacer, PageBreak, Table, TableStyle
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import os

def generate_pdf(output_pdf, summary, text_files, image_files):
    doc = SimpleDocTemplate(output_pdf, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    # Title
    elements.append(Paragraph("Simulation Results", styles["Title"]))
    elements.append(Spacer(1, 20))
    game_summary = summary.replace("\n", "<br/>").replace("\t", "    ")
    paragraph = Paragraph(game_summary, styles["Normal"])
    elements.append(paragraph)
    elements.append(Spacer(1, 20))

    # Efficiency summary
    elements.append(Paragraph(f"<b>Efficiency summary</b>", styles["Heading2"]))
    with open(text_files[0], "r") as f:
        for line in f:
            elements.append(Paragraph(line.strip(), styles["Normal"]))
    elements.append(Image(image_files[0], width=400, height=300))
    elements.append(Spacer(1, 20))

    # Game outcome summary
    elements.append(Paragraph(f"<b>Game outcomes</b>", styles["Heading2"]))
    elements.append(Image(image_files[1], width=400, height=300))
    elements.append(Image(image_files[2], width=400, height=300))
    elements.append(Spacer(1, 20))

    # Combat quality summary
    elements.append(Paragraph(f"<b>Combat move quality throughout the games</b>", styles["Heading2"]))
    with open(text_files[1], "r") as f:
        for line in f:
            elements.append(Paragraph(line.strip(), styles["Normal"]))
    elements.append(Image(image_files[3], width=400, height=300))
    elements.append(Image(image_files[4], width=400, height=300))
    elements.append(Spacer(1, 20))

    # Profiling summary
    elements.append(Paragraph(f"<b>Profiling of MCTS algorithm</b>", styles["Heading2"]))
    elements.append(Image(image_files[5], width=400, height=300))
    elements.append(Image(image_files[6], width=400, height=300))
    elements.append(Spacer(1, 20))
    # elements.append(PageBreak())

    doc.build(elements)

parser = argparse.ArgumentParser()
parser.add_argument("--file_name", type=str, required=True)
parser.add_argument("--report_folder", type=str, required=True)
parser.add_argument("--game_summary", type=str, required=True)
args = parser.parse_args()

file_name = args.file_name
report_folder = args.report_folder
summary = args.game_summary

generate_pdf(
    file_name,
    summary,
    text_files=[
        f"{report_folder}/metrics/efficiency_summary.txt",
        # f"{report_folder}/metrics/reduction_summary.txt",
        f"{report_folder}/metrics/combat_quality_averages.txt",
    ],
    image_files=[
        # f"{report_folder}/metrics/efficiency_plot.png",
        f"{report_folder}/metrics/aggregate_game_summary.png",
        # f"{report_folder}/metrics/total_vs_pruned.png",
        # f"{report_folder}/metrics/reduction_per_round.png",
        f"{report_folder}/metrics/win_vs_lost.png",
        f"{report_folder}/metrics/outcome_vs_rounds.png",
        f"{report_folder}/metrics/combat_quality_trajectories.png",
        f"{report_folder}/metrics/combat_quality_metrics.png",
        f"{report_folder}/profiling/stacked_runtime_composition.png",
        f"{report_folder}/profiling/boxplot_function_time.png",
    ]
)

print("Report pdf ready")
