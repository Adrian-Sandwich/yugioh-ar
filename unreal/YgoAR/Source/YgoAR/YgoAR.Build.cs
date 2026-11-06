using UnrealBuildTool;

public class YgoAR : ModuleRules
{
	public YgoAR(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "DeveloperSettings" });
		PrivateDependencyModuleNames.AddRange(new string[] {
			"HTTP", "Json", "ImageWrapper", "RenderCore", "RHI", "Slate", "SlateCore", "UMG", "InputCore"
		});
	}
}
